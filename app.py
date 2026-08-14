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
        h_value, t_value = _safe_float(h_val), _safe_float(t_val)
    else:
        h_val = t_val = None
        condition_text, sheet_data, sheet_plot = "", "Data", "Plots"
        dl_filename = f"AQWA_Analysis_{stem}.xlsx"
        h_value = t_value = None

    return {
        "df": df_merged,
        "condition_text": condition_text,
        "sheet_data": sheet_data,
        "sheet_plot": sheet_plot,
        "dl_filename": dl_filename,
        "h_val": h_val,
        "t_val": t_val,
        "h_value": h_value,
        "t_value": t_value,
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


def compute_steady_stats(df, present_cols, cutoff):
    df_steady = df[df["Time_s"] > cutoff]
    if df_steady.empty:
        return pd.DataFrame()
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
    return pd.DataFrame(stats_rows)


def render_case(fname, result, key_suffix):
    """แสดงกราฟ/สถิติ/ปุ่มดาวน์โหลดสำหรับไฟล์เคสเดียว (เรียกซ้ำได้หลายครั้งเมื่ออัปโหลดหลายไฟล์)."""
    df = result["df"]
    condition_text = result["condition_text"]
    present_cols = [c for c in df.columns if c != "Time_s"]

    if "Time_s" not in df.columns or df.empty:
        st.error("⚠️ ไม่พบคอลัมน์เวลา (Time) หรือไม่มีข้อมูลที่อ่านได้ในไฟล์นี้")
        return
    if not present_cols:
        st.error("⚠️ อ่านไฟล์ได้ แต่ไม่พบตัวแปรที่รู้จัก (Wave/Heave/Tension/RX/RY/RZ)")
        st.info("ลองตรวจสอบ Metadata header ในไฟล์ต้นฉบับ (บรรทัด 'Line X: ...' ที่อธิบายว่าแต่ละ Line คือตัวแปรอะไร)")
        return

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
        st.plotly_chart(fig, use_container_width=True, key=f"dual_{key_suffix}")

        st.plotly_chart(
            line_chart(df, ["Wave_m", "Heave_m"], [COLOR_MAP["Wave_m"], COLOR_MAP["Heave_m"]],
                       "Buoy Heave vs Wave Elevation (Single Y-Axis)", "Elevation (m)", condition_text),
            use_container_width=True, key=f"single_{key_suffix}",
        )
    elif has_wave:
        st.plotly_chart(
            line_chart(df, ["Wave_m"], [COLOR_MAP["Wave_m"]], "Wave Elevation", "Wave (m)", condition_text),
            use_container_width=True, key=f"wave_{key_suffix}",
        )
    elif has_heave:
        st.plotly_chart(
            line_chart(df, ["Heave_m"], [COLOR_MAP["Heave_m"]], "Heave Response", "Heave (m)", condition_text),
            use_container_width=True, key=f"heave_{key_suffix}",
        )

    if tension_cols:
        st.plotly_chart(
            line_chart(df, tension_cols, TENSION_COLORS[: len(tension_cols)],
                       "Mooring Line Tension", "Tension (kN)", condition_text),
            use_container_width=True, key=f"tension_{key_suffix}",
        )

    if len(rot_cols) >= 2:
        st.plotly_chart(
            line_chart(df, rot_cols, [COLOR_MAP[c] for c in rot_cols],
                       "Rotational Response (Combined)", "Rotation (deg)", condition_text),
            use_container_width=True, key=f"rot_combined_{key_suffix}",
        )

    if "RX_deg" in df.columns and "RY_deg" in df.columns:
        st.plotly_chart(
            line_chart(df, ["RX_deg", "RY_deg"], [COLOR_MAP["RX_deg"], COLOR_MAP["RY_deg"]],
                       "Rotational Response: RX vs RY", "Rotation (deg)", condition_text),
            use_container_width=True, key=f"rxry_{key_suffix}",
        )
    elif len(rot_cols) == 1:
        c = rot_cols[0]
        st.plotly_chart(
            line_chart(df, [c], [COLOR_MAP[c]], f"Rotational Response ({c})", "Rotation (deg)", condition_text),
            use_container_width=True, key=f"rot_single_{key_suffix}",
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
        st.plotly_chart(fig, use_container_width=True, key=f"rot_sep_{key_suffix}")

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
        key=f"cutoff_{key_suffix}",
    )

    df_stats = compute_steady_stats(df, present_cols, cutoff)
    if df_stats.empty:
        st.warning("ไม่มีข้อมูลเหลือหลังตัด Transient ลองปรับค่าลง")
    else:
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
        key=f"download_{key_suffix}",
    )


def render_comparison(cases):
    """สรุปเปรียบเทียบทุกเคส (หลาย H/T) ในตารางและกราฟเดียว ใช้ cutoff เดียวกันทุกเคสเพื่อให้เทียบกันได้จริง"""
    st.markdown("---")
    st.subheader("🧮 เปรียบเทียบทุกเคส (Comparison Across Cases)")

    max_t = max(float(r["df"]["Time_s"].max()) for _, r in cases)
    global_cutoff = st.number_input(
        "ตัดช่วง Transient เริ่มต้น (วินาที) — ใช้ค่าเดียวกันทุกเคสเพื่อเปรียบเทียบอย่างเป็นธรรม",
        min_value=0.0, max_value=max_t, value=min(50.0, max_t), step=5.0,
    )

    summary_rows = []
    for fname, result in cases:
        df = result["df"]
        present_cols = [c for c in df.columns if c != "Time_s"]
        df_stats = compute_steady_stats(df, present_cols, global_cutoff)
        row = {
            "File": fname,
            "H": result["h_value"] if result["h_value"] is not None else result["h_val"],
            "T": result["t_value"] if result["t_value"] is not None else result["t_val"],
        }
        amp_by_param = dict(zip(df_stats.get("Parameter", []), df_stats.get("Amplitude", [])))
        max_by_param = dict(zip(df_stats.get("Parameter", []), df_stats.get("Max", [])))
        if "Wave_m" in amp_by_param:
            row["Wave Amp (m)"] = amp_by_param["Wave_m"]
        if "Heave_m" in amp_by_param:
            row["Heave Amp (m)"] = amp_by_param["Heave_m"]
        if "Wave_m" in amp_by_param and "Heave_m" in amp_by_param and amp_by_param["Wave_m"]:
            row["RAO (Heave/Wave)"] = amp_by_param["Heave_m"] / amp_by_param["Wave_m"]
        for param, max_val in max_by_param.items():
            if param.startswith("Tension"):
                row[f"Max {param}"] = max_val
        summary_rows.append(row)

    df_summary = pd.DataFrame(summary_rows).sort_values(
        by=[c for c in ["H", "T"] if c in summary_rows[0]] or ["File"], na_position="last"
    ).reset_index(drop=True)

    st.dataframe(
        df_summary.style.format({c: "{:.4f}" for c in df_summary.columns if c not in ("File", "H", "T")}),
        use_container_width=True,
    )

    if "RAO (Heave/Wave)" in df_summary.columns and df_summary["RAO (Heave/Wave)"].notna().any():
        x_col = "T" if df_summary["T"].notna().any() else "File"
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=df_summary[x_col], y=df_summary["RAO (Heave/Wave)"],
            mode="lines+markers", name="RAO (Heave/Wave)",
            line=dict(color=COLOR_MAP["Heave_m"]),
        ))
        fig.update_layout(
            title="RAO (Heave/Wave) เทียบระหว่างเคส",
            xaxis_title="Wave Period T (s)" if x_col == "T" else "File",
            yaxis_title="RAO (Heave/Wave)",
            height=380,
        )
        st.plotly_chart(fig, use_container_width=True, key="comparison_rao_chart")

    st.download_button(
        "💾 Download Comparison Summary (.csv)",
        data=df_summary.to_csv(index=False).encode("utf-8-sig"),
        file_name="AQWA_Comparison_Summary.csv",
        mime="text/csv",
        key="download_comparison",
    )


st.title("🌊 AQWA Wave Analyzer")
st.markdown(
    "อัปโหลดไฟล์ CSV จาก AQWA ได้ทีละหลายไฟล์ (รองรับไฟล์ Raw โดยตรง รวมถึงเคสที่มีเส้นสมอหลายเส้น หรือมีแค่บางตัวแปร) "
    "โปรแกรมจะสร้างกราฟแบบ Interactive พร้อมสรุปสถิติ/RAO ต่อเคส และเปรียบเทียบข้ามเคส (หลายความสูงคลื่น/คาบ) ส่งออกเป็น Excel/CSV ได้"
)

uploaded_files = st.file_uploader(
    "📥 อัปโหลดไฟล์ CSV ของคุณ (เลือกได้หลายไฟล์พร้อมกัน)",
    accept_multiple_files=True, type=["csv"],
)

if uploaded_files:
    cases = []
    for f in uploaded_files:
        with st.spinner(f"กำลังอ่านและประมวลผลไฟล์ {f.name} ..."):
            try:
                result = parse_aqwa_file(f.getvalue(), f.name)
            except Exception as e:
                st.error(f"⚠️ {f.name}: เกิดข้อผิดพลาดในการอ่านไฟล์ - {e}")
                continue
        cases.append((f.name, result))

    if not cases:
        st.stop()

    cases.sort(key=lambda item: (
        item[1]["h_value"] if item[1]["h_value"] is not None else float("inf"),
        item[1]["t_value"] if item[1]["t_value"] is not None else float("inf"),
        item[0],
    ))

    if len(cases) > 1:
        render_comparison(cases)
        st.markdown("---")
        st.subheader("📂 รายละเอียดแต่ละเคส")
        tabs = st.tabs([fname for fname, _ in cases])
        for tab, (fname, result) in zip(tabs, cases):
            with tab:
                render_case(fname, result, key_suffix=fname)
    else:
        fname, result = cases[0]
        render_case(fname, result, key_suffix=fname)
