import io
import re

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

st.set_page_config(page_title="AQWA Wave Analyzer", page_icon="🌊", layout="wide")

COLOR_MAP = {
    "Wave_m": "#4169E1",
    "Heave_m": "#B22222",
    "RX_deg": "#FF8C00",
    "RY_deg": "#2E8B57",
    "RZ_deg": "#8A2BE2",
}
TENSION_COLORS = ["#800000", "#B8860B", "#4B0082", "#006400", "#2F4F4F", "#C71585"]


def classify(text_lower):
    """Map a metadata description or column header to a standard quantity name."""
    if "wave" in text_lower:
        return "Wave_m"
    if "global z" in text_lower or "heave" in text_lower:
        return "Heave_m"
    if "cable" in text_lower or "tension" in text_lower:
        return "Tension_N"
    if "rx" in text_lower or "roll" in text_lower:
        return "RX_deg"
    if "ry" in text_lower or "pitch" in text_lower:
        return "RY_deg"
    if "rz" in text_lower or "yaw" in text_lower:
        return "RZ_deg"
    return None


def _safe_float(text):
    match = re.search(r"[-+]?\d*\.?\d+", text)
    return float(match.group()) if match else None


def _parse_aqwa(file_bytes, filename):
    content = file_bytes.decode("latin1")
    lines = content.split("\n")

    # ---------------------------------------------------------
    # ระบบวิเคราะห์ Header และ Metadata อัตโนมัติ (อ่านไฟล์ดิบ AQWA)
    # ---------------------------------------------------------
    skip_rows = 0
    mapping = {}  # เช่น "line a" -> "Heave_m" (รองรับหลาย Line ที่เป็นตัวแปรเดียวกัน เช่น Tension หลายเส้น)

    for i, line in enumerate(lines):
        cells = line.split(",")
        first_cell = cells[0].strip()
        line_lower = line.lower()

        if first_cell.lower().startswith("line ") and ":" in first_cell:
            line_id = first_cell.split(":")[0].strip().lower()
            category = classify(line_lower)
            if category:
                mapping[line_id] = category

        if "time" in line_lower and len(cells) >= 4:
            skip_rows = i
            break

    df_raw = pd.read_csv(io.StringIO(content), skiprows=skip_rows)

    # ---------------------------------------------------------
    # จับคู่คอลัมน์ดิบ -> ชื่อมาตรฐาน (รองรับเส้นสมอ/Tension หลายเส้น แทนที่จะทับกันเหลือเส้นเดียว)
    # ---------------------------------------------------------
    classified_cols = []
    for col in df_raw.columns:
        col_lower = col.lower()
        if "time" in col_lower:
            classified_cols.append((col, "Time_s"))
            continue
        category = classify(col_lower)
        if category is None:
            for line_id, mapped_category in mapping.items():
                if line_id in col_lower:
                    category = mapped_category
                    break
        classified_cols.append((col, category))

    tension_total = sum(1 for _, cat in classified_cols if cat == "Tension_N")

    df_merged = pd.DataFrame()
    rename_report = []
    tension_idx = 0
    for col, category in classified_cols:
        if category is None:
            rename_report.append((col, None))
            continue
        if category == "Time_s":
            df_merged["Time_s"] = df_raw[col]
        elif category == "Tension_N":
            tension_idx += 1
            col_lower = col.lower()
            values = df_raw[col] if "kn" in col_lower else df_raw[col] / 1000.0
            name = "Tension_kN" if tension_total <= 1 else f"Tension_{tension_idx}_kN"
            df_merged[name] = values
            category = name
        else:
            df_merged[category] = df_raw[col]
        rename_report.append((col, category))

    df_merged = df_merged.apply(pd.to_numeric, errors="coerce")
    rows_before = len(df_merged)
    if "Time_s" in df_merged.columns:
        df_merged = df_merged.dropna(subset=["Time_s"]).sort_values("Time_s").reset_index(drop=True)
    rows_after = len(df_merged)

    nan_counts = df_merged.isna().sum()
    nan_counts = {k: int(v) for k, v in nan_counts[nan_counts > 0].items()}

    # ---------------------------------------------------------
    # ดึงเงื่อนไข (H และ T) จากชื่อไฟล์ ถ้ามี
    # ---------------------------------------------------------
    stem = filename.rsplit(".", 1)[0] if "." in filename else filename
    parts = stem.split("-")
    if len(parts) >= 2:
        h_val, t_val = parts[0], parts[1]
        condition_text = f"(Condition: H={h_val}, T={t_val})"
        sheet_data, sheet_plot = f"Data_{h_val}_{t_val}", f"Plot_{h_val}_{t_val}"
        dl_filename = f"AQWA_Result_{h_val}_{t_val}.xlsx"
        h_value = _safe_float(h_val)
    else:
        condition_text, sheet_data, sheet_plot = "", "Data", "Plots"
        dl_filename = f"AQWA_Analysis_{stem}.xlsx"
        h_value = None

    return {
        "df": df_merged,
        "condition_text": condition_text,
        "sheet_data": sheet_data,
        "sheet_plot": sheet_plot,
        "dl_filename": dl_filename,
        "h_value": h_value,
        "rename_report": rename_report,
        "rows_before": rows_before,
        "rows_after": rows_after,
        "nan_counts": nan_counts,
        "raw_preview": df_raw.head(20),
    }


@st.cache_data(show_spinner=False)
def parse_aqwa_file(file_bytes, filename):
    return _parse_aqwa(file_bytes, filename)


def compute_matched_ylim(s1, s2, pad=1.2):
    """ช่วงแกนแบบล็อคสเกลเดียวกันสำหรับกราฟ Dual Axis (ให้เห็น phase ระหว่างสองสัญญาณได้ตรงกัน)."""
    span = max(s1.max() - s1.min(), s2.max() - s2.min()) * pad
    if span <= 0:
        span = 1.0
    mid1, mid2 = (s1.max() + s1.min()) / 2, (s2.max() + s2.min()) / 2
    return (mid1 - span / 2, mid1 + span / 2), (mid2 - span / 2, mid2 + span / 2)


def line_chart(df, cols, colors, title, y_title, condition_text, height=380):
    fig = go.Figure()
    for col, color in zip(cols, colors):
        fig.add_trace(go.Scatter(x=df["Time_s"], y=df[col], name=col, line=dict(color=color)))
    subtitle = f"<br><sup>{condition_text}</sup>" if condition_text else ""
    fig.update_layout(
        title=f"{title}{subtitle}",
        xaxis_title="Time (s)",
        yaxis_title=y_title,
        height=height,
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    return fig


def build_excel_bytes(df, df_stats, condition_text, sheet_data, sheet_plot, has_wave, has_heave, tension_cols, rot_cols):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        df.to_excel(writer, sheet_name=sheet_data, index=False)
        if not df_stats.empty:
            df_stats.to_excel(writer, sheet_name="Summary_Stats", index=False)

        workbook = writer.book
        worksheet_summary = workbook.add_worksheet(sheet_plot)
        worksheet_summary.set_column("A:C", 20)
        max_row = len(df)
        col_time = df.columns.get_loc("Time_s")

        def excel_chart(title, y_name, cols, colors, legend=True):
            chart = workbook.add_chart({"type": "line"})
            for col, color in zip(cols, colors):
                idx = df.columns.get_loc(col)
                chart.add_series({
                    "name": [sheet_data, 0, idx],
                    "categories": [sheet_data, 1, col_time, max_row, col_time],
                    "values": [sheet_data, 1, idx, max_row, idx],
                    "line": {"color": color, "width": 1.5},
                })
            chart.set_title({"name": title})
            chart.set_x_axis({"name": "Time (s)",
                               "major_gridlines": {"visible": True, "line": {"color": "#D9D9D9"}}})
            chart.set_y_axis({"name": y_name,
                               "major_gridlines": {"visible": True, "line": {"color": "#D9D9D9"}}})
            chart.set_plotarea({"fill": {"none": True}})
            chart.set_size({"width": 800, "height": 320})
            if not legend:
                chart.set_legend({"position": "none"})
            return chart

        row = 2
        if has_wave and has_heave:
            idx_wave, idx_heave = df.columns.get_loc("Wave_m"), df.columns.get_loc("Heave_m")
            chart_dual = workbook.add_chart({"type": "line"})
            chart_dual.add_series({
                "name": [sheet_data, 0, idx_wave],
                "categories": [sheet_data, 1, col_time, max_row, col_time],
                "values": [sheet_data, 1, idx_wave, max_row, idx_wave],
                "line": {"color": COLOR_MAP["Wave_m"], "width": 1.5},
            })
            chart_dual.add_series({
                "name": [sheet_data, 0, idx_heave],
                "categories": [sheet_data, 1, col_time, max_row, col_time],
                "values": [sheet_data, 1, idx_heave, max_row, idx_heave],
                "y2_axis": True,
                "line": {"color": COLOR_MAP["Heave_m"], "width": 1.5},
            })
            chart_dual.set_title({"name": f"Buoy Heave vs Wave Elevation (Dual Axis)\n{condition_text}"})
            chart_dual.set_x_axis({"name": "Time (s)",
                                    "major_gridlines": {"visible": True, "line": {"color": "#D9D9D9"}}})
            chart_dual.set_y_axis({"name": "Wave Elevation (m)",
                                    "major_gridlines": {"visible": True, "line": {"color": "#D9D9D9"}}})
            chart_dual.set_y2_axis({"name": "Heave Response (m)"})
            chart_dual.set_plotarea({"fill": {"none": True}})
            chart_dual.set_size({"width": 800, "height": 350})
            worksheet_summary.insert_chart(f"B{row}", chart_dual)
            row += 18

        normal_specs = []
        if has_wave and has_heave:
            normal_specs.append((f"Buoy Heave vs Wave Elevation (Single Axis)\n{condition_text}",
                                  "Elevation (m)", ["Wave_m", "Heave_m"],
                                  [COLOR_MAP["Wave_m"], COLOR_MAP["Heave_m"]], True))
        elif has_wave:
            normal_specs.append((f"Wave Elevation\n{condition_text}", "Wave (m)",
                                  ["Wave_m"], [COLOR_MAP["Wave_m"]], False))
        elif has_heave:
            normal_specs.append((f"Heave Response\n{condition_text}", "Heave (m)",
                                  ["Heave_m"], [COLOR_MAP["Heave_m"]], False))

        if tension_cols:
            normal_specs.append((f"Mooring Line Tension\n{condition_text}", "Tension (kN)",
                                  tension_cols, TENSION_COLORS[: len(tension_cols)], len(tension_cols) > 1))

        if len(rot_cols) >= 2:
            normal_specs.append((f"Rotational Response (Combined)\n{condition_text}", "Rotation (deg)",
                                  rot_cols, [COLOR_MAP[c] for c in rot_cols], True))

        if "RX_deg" in df.columns and "RY_deg" in df.columns:
            normal_specs.append((f"Rotational Response: RX vs RY\n{condition_text}", "Rotation (deg)",
                                  ["RX_deg", "RY_deg"], [COLOR_MAP["RX_deg"], COLOR_MAP["RY_deg"]], True))

        for c in rot_cols:
            normal_specs.append((f"{c} Response\n{condition_text}", c, [c], [COLOR_MAP[c]], False))

        for title, y_name, cols, colors, legend in normal_specs:
            worksheet_summary.insert_chart(f"B{row}", excel_chart(title, y_name, cols, colors, legend))
            row += 18

    return output.getvalue()


st.title("🌊 AQWA Wave Analyzer")
st.markdown(
    "อัปโหลดไฟล์ CSV จาก AQWA (รองรับไฟล์ Raw โดยตรง รวมถึงเคสที่มีเส้นสมอหลายเส้น หรือมีแค่บางตัวแปร) "
    "โปรแกรมจะสร้างกราฟแบบ Interactive พร้อมสรุปสถิติ/RAO และส่งออกเป็น Excel"
)

uploaded_file = st.file_uploader("📥 อัปโหลดไฟล์ CSV ของคุณ", accept_multiple_files=False, type=["csv"])

if uploaded_file:
    with st.spinner("กำลังอ่านและประมวลผลไฟล์..."):
        try:
            result = parse_aqwa_file(uploaded_file.getvalue(), uploaded_file.name)
        except Exception as e:
            st.error(f"เกิดข้อผิดพลาดในการอ่านไฟล์: {e}")
            st.stop()

    df = result["df"]
    condition_text = result["condition_text"]
    present_cols = [c for c in df.columns if c != "Time_s"]

    if "Time_s" not in df.columns or df.empty:
        st.error("⚠️ ไม่พบคอลัมน์เวลา (Time) หรือไม่มีข้อมูลที่อ่านได้ในไฟล์นี้")
    elif not present_cols:
        st.error("⚠️ อ่านไฟล์ได้ แต่ไม่พบตัวแปรที่รู้จัก (Wave/Heave/Tension/RX/RY/RZ)")
        st.info("ลองตรวจสอบ Metadata header ในไฟล์ต้นฉบับ (บรรทัด 'Line X: ...' ที่อธิบายว่าแต่ละ Line คือตัวแปรอะไร)")
    else:
        st.success(f"✅ อ่านไฟล์และจัดเรียงข้อมูลสำเร็จ! {condition_text}")

        unmatched = [c for c, cat in result["rename_report"] if cat is None]
        dropped = result["rows_before"] - result["rows_after"]
        with st.expander("🔍 รายละเอียดการอ่านไฟล์ (Column Mapping / Data Quality)"):
            st.write("**คอลัมน์ที่จับคู่ได้:**")
            st.table(pd.DataFrame(
                [(c, cat) for c, cat in result["rename_report"] if cat],
                columns=["Raw Column", "Mapped To"],
            ))
            if unmatched:
                st.warning(f"คอลัมน์ที่จับคู่ไม่ได้ ({len(unmatched)}): {', '.join(unmatched)}")
            if dropped > 0:
                st.warning(f"ทิ้งไป {dropped} แถว เนื่องจากอ่านค่าเวลา (Time) ไม่ได้ (แถวว่าง/ท้ายไฟล์)")
            if result["nan_counts"]:
                st.warning(
                    f"พบค่าว่าง/อ่านไม่ได้บางจุดในคอลัมน์: {result['nan_counts']} "
                    "(จุดเหล่านี้จะแสดงเป็นช่องว่างในกราฟ ไม่ถูกลบทิ้งทั้งแถว)"
                )
            st.write("**ตัวอย่างข้อมูลดิบ (20 แถวแรกหลังตัด Header):**")
            st.dataframe(result["raw_preview"], use_container_width=True)

        tension_cols = [c for c in df.columns if c.startswith("Tension")]
        rot_cols = [c for c in ["RX_deg", "RY_deg", "RZ_deg"] if c in df.columns]
        has_wave, has_heave = "Wave_m" in df.columns, "Heave_m" in df.columns

        # ==========================================
        # กราฟ Interactive (Plotly)
        # ==========================================
        st.subheader("📈 กราฟวิเคราะห์ผล (Interactive Plots)")

        if has_wave and has_heave:
            (wlo, whi), (hlo, hhi) = compute_matched_ylim(df["Wave_m"].dropna(), df["Heave_m"].dropna())
            fig = make_subplots(specs=[[{"secondary_y": True}]])
            fig.add_trace(go.Scatter(x=df["Time_s"], y=df["Wave_m"], name="Wave Elevation",
                                      line=dict(color=COLOR_MAP["Wave_m"])), secondary_y=False)
            fig.add_trace(go.Scatter(x=df["Time_s"], y=df["Heave_m"], name="Heave Response",
                                      line=dict(color=COLOR_MAP["Heave_m"])), secondary_y=True)
            fig.update_yaxes(title_text="Wave (m)", range=[wlo, whi], secondary_y=False)
            fig.update_yaxes(title_text="Heave (m)", range=[hlo, hhi], secondary_y=True)
            fig.update_xaxes(title_text="Time (s)")
            fig.update_layout(
                title=f"Buoy Heave vs Wave Elevation (Dual Axis)<br><sup>{condition_text}</sup>",
                height=420, hovermode="x unified",
            )
            st.plotly_chart(fig, use_container_width=True)

            st.plotly_chart(
                line_chart(df, ["Wave_m", "Heave_m"], [COLOR_MAP["Wave_m"], COLOR_MAP["Heave_m"]],
                           "Buoy Heave vs Wave Elevation (Single Y-Axis)", "Elevation (m)", condition_text),
                use_container_width=True,
            )
        elif has_wave:
            st.plotly_chart(
                line_chart(df, ["Wave_m"], [COLOR_MAP["Wave_m"]], "Wave Elevation", "Wave (m)", condition_text),
                use_container_width=True,
            )
        elif has_heave:
            st.plotly_chart(
                line_chart(df, ["Heave_m"], [COLOR_MAP["Heave_m"]], "Heave Response", "Heave (m)", condition_text),
                use_container_width=True,
            )

        if tension_cols:
            st.plotly_chart(
                line_chart(df, tension_cols, TENSION_COLORS[: len(tension_cols)],
                           "Mooring Line Tension", "Tension (kN)", condition_text),
                use_container_width=True,
            )

        if len(rot_cols) >= 2:
            st.plotly_chart(
                line_chart(df, rot_cols, [COLOR_MAP[c] for c in rot_cols],
                           "Rotational Response (Combined)", "Rotation (deg)", condition_text),
                use_container_width=True,
            )

        if "RX_deg" in df.columns and "RY_deg" in df.columns:
            st.plotly_chart(
                line_chart(df, ["RX_deg", "RY_deg"], [COLOR_MAP["RX_deg"], COLOR_MAP["RY_deg"]],
                           "Rotational Response: RX vs RY", "Rotation (deg)", condition_text),
                use_container_width=True,
            )
        elif len(rot_cols) == 1:
            c = rot_cols[0]
            st.plotly_chart(
                line_chart(df, [c], [COLOR_MAP[c]], f"Rotational Response ({c})", "Rotation (deg)", condition_text),
                use_container_width=True,
            )

        if rot_cols:
            st.markdown("##### กราฟแยกทีละแกน (Separated Axes)")
            fig = make_subplots(rows=len(rot_cols), cols=1, shared_xaxes=True, subplot_titles=rot_cols)
            for i, c in enumerate(rot_cols, start=1):
                fig.add_trace(go.Scatter(x=df["Time_s"], y=df[c], name=c, line=dict(color=COLOR_MAP[c])),
                              row=i, col=1)
            fig.update_xaxes(title_text="Time (s)", row=len(rot_cols), col=1)
            fig.update_layout(
                height=280 * len(rot_cols),
                title=f"Rotational Response (Separated)<br><sup>{condition_text}</sup>",
                showlegend=False,
            )
            st.plotly_chart(fig, use_container_width=True)

        # ==========================================
        # สรุปสถิติ & RAO (Steady-State Analysis)
        # ==========================================
        st.markdown("---")
        st.subheader("📐 สรุปผลสถิติ & RAO (Steady-State Analysis)")

        t_min, t_max = float(df["Time_s"].min()), float(df["Time_s"].max())
        default_cutoff = min(50.0, t_max) if t_max > t_min else t_min
        cutoff = st.slider(
            "ตัดช่วง Transient เริ่มต้น (คำนวณสถิติ/RAO จากข้อมูลหลังวินาทีที่เลือกเท่านั้น)",
            min_value=t_min, max_value=t_max, value=default_cutoff,
            step=max((t_max - t_min) / 100, 0.1) if t_max > t_min else 1.0,
        )

        df_steady = df[df["Time_s"] > cutoff]
        df_stats = pd.DataFrame()
        if df_steady.empty:
            st.warning("ไม่มีข้อมูลเหลือหลังตัด Transient ลองปรับค่าลง")
        else:
            stats_rows = []
            for col in present_cols:
                series = df_steady[col].dropna()
                if series.empty:
                    continue
                vmax, vmin = series.max(), series.min()
                stats_rows.append({
                    "Parameter": col, "Max": vmax, "Min": vmin,
                    "Amplitude": (vmax - vmin) / 2, "Mean": series.mean(),
                })
            df_stats = pd.DataFrame(stats_rows)

            if has_wave and has_heave:
                wave_amp = df_stats.loc[df_stats["Parameter"] == "Wave_m", "Amplitude"]
                heave_amp = df_stats.loc[df_stats["Parameter"] == "Heave_m", "Amplitude"]
                if len(wave_amp) and len(heave_amp) and wave_amp.iloc[0] != 0:
                    rao = heave_amp.iloc[0] / wave_amp.iloc[0]
                    col_a, col_b = st.columns(2)
                    col_a.metric("RAO (Heave/Wave)", f"{rao:.3f}")
                    if result["h_value"] and heave_amp.iloc[0] != 0:
                        hs_ratio = result["h_value"] / heave_amp.iloc[0]
                        col_b.metric("Hs / Heave Amplitude", f"{hs_ratio:.3f}")

            st.dataframe(
                df_stats.style.format({"Max": "{:.4f}", "Min": "{:.4f}", "Amplitude": "{:.4f}", "Mean": "{:.4f}"}),
                use_container_width=True,
            )

        # ==========================================
        # ส่งออก Excel
        # ==========================================
        st.markdown("---")
        st.subheader("📥 ส่งออกข้อมูล (Export to Excel)")

        excel_bytes = build_excel_bytes(
            df, df_stats, condition_text, result["sheet_data"], result["sheet_plot"],
            has_wave, has_heave, tension_cols, rot_cols,
        )
        st.download_button(
            label="💾 Download Results (.xlsx)",
            data=excel_bytes,
            file_name=result["dl_filename"],
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary",
        )
