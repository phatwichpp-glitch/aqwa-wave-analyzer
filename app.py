import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import io

st.set_page_config(page_title="AQWA Data Analyzer", layout="wide")

st.title("🌊 AQWA Time-Series Analyzer (Single File + All Plots)")
st.markdown("อัปโหลดไฟล์ CSV 1 ไฟล์ (รองรับไฟล์ Raw จาก AQWA โดยตรง) โปรแกรมจะสร้างกราฟทุกรูปแบบพร้อมส่งออกเป็น Excel")

uploaded_file = st.file_uploader(
    "📥 อัปโหลดไฟล์ CSV ของคุณ", 
    accept_multiple_files=False, 
    type=['csv']
)

if uploaded_file:
    try:
        # ดึงชื่อไฟล์มาตั้งเป็นเงื่อนไข (ถ้ามี)
        filename = uploaded_file.name
        parts = filename.replace('.csv', '').split('-')
        if len(parts) >= 2:
            h_val, t_val = parts[0], parts[1]
            condition_text = f"(Condition: H={h_val}, T={t_val})"
            sheet_data, sheet_plot = f"Data_{h_val}_{t_val}", f"Plot_{h_val}_{t_val}"
            dl_filename = f"AQWA_Result_{h_val}_{t_val}.xlsx"
        else:
            condition_text, sheet_data, sheet_plot, dl_filename = "", "Data", "Plots", f"AQWA_Analysis_{filename.replace('.csv', '')}.xlsx"

        # ---------------------------------------------------------
        # ระบบวิเคราะห์ Header และ Metadata อัตโนมัติ (อ่านไฟล์ดิบ AQWA)
        # ---------------------------------------------------------
        content = uploaded_file.getvalue().decode('latin1')
        lines = content.split('\n')
        
        skip_rows = 0
        mapping = {}
        
        for i, line in enumerate(lines):
            cells = line.split(',')
            first_cell = cells[0].strip()
            line_lower = line.lower()
            
            # 1. จับคู่ชื่อ Line (A, B, C...) กับตัวแปรจากคำอธิบาย
            if first_cell.lower().startswith("line ") and ":" in first_cell:
                line_id = first_cell.split(":")[0].strip().lower() # จะได้คำว่า "line a"
                if "wave" in line_lower: mapping[line_id] = "Wave_m"
                elif "global z" in line_lower or "heave" in line_lower: mapping[line_id] = "Heave_m"
                elif "cable" in line_lower or "tension" in line_lower: mapping[line_id] = "Tension_N"
                elif "rx" in line_lower or "roll" in line_lower: mapping[line_id] = "RX_deg"
                elif "ry" in line_lower or "pitch" in line_lower: mapping[line_id] = "RY_deg"
                elif "rz" in line_lower or "yaw" in line_lower: mapping[line_id] = "RZ_deg"
                
            # 2. หาบรรทัดเริ่มตารางข้อมูล (ต้องมีคำว่า Time และมีคอลัมน์มากกว่า 3 เพื่อตัดปัญหาบรรทัดแรก)
            if "time" in line_lower and len(cells) >= 4:
                skip_rows = i
                break
                
        # รีเซ็ตตำแหน่งไฟล์แล้วอ่านด้วย Pandas
        uploaded_file.seek(0)
        df = pd.read_csv(uploaded_file, encoding='latin1', skiprows=skip_rows)
        
        # สร้าง DataFrame ใหม่ที่ชื่อคอลัมน์เป็นมาตรฐานเดียวกัน
        df_merged = pd.DataFrame()
        
        for col in df.columns:
            col_lower = col.lower()
            if "time" in col_lower: 
                df_merged['Time_s'] = df[col]
                continue
                
            # ตรวจสอบว่าคอลัมน์นี้ถูกตั้งชื่อไว้ตรงๆ หรือไม่
            matched = False
            if "wave" in col_lower: df_merged['Wave_m'] = df[col]; matched = True
            elif "heave" in col_lower: df_merged['Heave_m'] = df[col]; matched = True
            elif "tension" in col_lower: 
                df_merged['Tension_kN'] = df[col] if "kn" in col_lower else df[col] / 1000.0
                matched = True
            elif "rx" in col_lower or "roll" in col_lower: df_merged['RX_deg'] = df[col]; matched = True
            elif "ry" in col_lower or "pitch" in col_lower: df_merged['RY_deg'] = df[col]; matched = True
            elif "rz" in col_lower or "yaw" in col_lower: df_merged['RZ_deg'] = df[col]; matched = True
            
            # ถ้าไม่เจอแบบตรงๆ ให้เช็คจาก Mapping ที่อ่านมาจาก Metadata ด้านบน
            if not matched:
                for line_id, var_name in mapping.items():
                    if line_id in col_lower: # เช่น ถ้ามีคำว่า "line a" ในชื่อคอลัมน์ "Line A (m)"
                        if var_name == "Tension_N":
                            df_merged['Tension_kN'] = df[col] if "kn" in col_lower else df[col] / 1000.0
                        else:
                            df_merged[var_name] = df[col]
                        break

        # ตรวจสอบว่าคอลัมน์มาครบหรือไม่
        expected_cols = ['Time_s', 'Wave_m', 'Heave_m', 'Tension_kN', 'RX_deg', 'RY_deg', 'RZ_deg']
        missing_cols = [c for c in expected_cols if c not in df_merged.columns]

        if missing_cols:
            st.error(f"⚠️ ข้อมูลไม่ครบ! ไม่พบคอลัมน์ที่ตรงกับตัวแปรต่อไปนี้: {', '.join(missing_cols)}")
            st.info("โปรแกรมพยายามอ่าน Metadata แล้ว แต่ไม่พบคำอธิบายของตัวแปรที่ขาดหายไปครับ")
        else:
            # แปลงข้อมูลให้เป็นตัวเลขทั้งหมด และลบบรรทัดที่มีค่าว่าง
            df_merged = df_merged.apply(pd.to_numeric, errors='coerce').dropna()

            # คณิตศาสตร์ล็อคสเกลแกนซ้ายขวา (สำหรับกราฟ Dual Axis)
            w_min, w_max = df_merged['Wave_m'].min(), df_merged['Wave_m'].max()
            h_min, h_max = df_merged['Heave_m'].min(), df_merged['Heave_m'].max()
            target_range = max(w_max - w_min, h_max - h_min) * 1.2
            w_mid = (w_max + w_min) / 2.0
            h_mid = (h_max + h_min) / 2.0
            wave_min_limit, wave_max_limit = w_mid - target_range / 2, w_mid + target_range / 2
            heave_min_limit, heave_max_limit = h_mid - target_range / 2, h_mid + target_range / 2

            st.success(f"✅ อ่านไฟล์และจัดเรียงข้อมูลสำเร็จ! {condition_text}")

            # ==========================================
            # สร้างกราฟบนหน้าเว็บ
            # ==========================================
            st.subheader("📈 กราฟวิเคราะห์ผล (Interactive Plots)")
            
            # กราฟ 1A: Wave & Heave (Dual Axis)
            fig1, ax1 = plt.subplots(figsize=(10, 4))
            fig1.patch.set_facecolor('white')
            ax1.set_facecolor('white')
            ax1.plot(df_merged['Time_s'], df_merged['Wave_m'], color='#4169E1', label='Wave Elevation', linewidth=1.5)
            ax1.set_xlabel('Time (s)')
            ax1.set_ylabel('Wave (m)', color='#4169E1')
            ax1.tick_params(axis='y', labelcolor='#4169E1')
            ax1.set_ylim([wave_min_limit, wave_max_limit])
            ax1.grid(visible=True, linestyle='--', color='lightgray', alpha=0.7)
            
            ax2 = ax1.twinx()
            ax2.plot(df_merged['Time_s'], df_merged['Heave_m'], color='#B22222', label='Heave Response', linewidth=1.5)
            ax2.set_ylabel('Heave (m)', color='#B22222')
            ax2.tick_params(axis='y', labelcolor='#B22222')
            ax2.set_ylim([heave_min_limit, heave_max_limit])
            
            plt.title(f'Buoy Heave vs Wave Elevation (Dual Axis)\n{condition_text}', fontsize=12, fontweight='bold')
            fig1.tight_layout()
            st.pyplot(fig1)

            # กราฟ 1B: Wave & Heave (Single Axis)
            fig1b, ax1b = plt.subplots(figsize=(10, 4))
            fig1b.patch.set_facecolor('white')
            ax1b.set_facecolor('white')
            ax1b.plot(df_merged['Time_s'], df_merged['Wave_m'], color='#4169E1', label='Wave Elevation', linewidth=1.5)
            ax1b.plot(df_merged['Time_s'], df_merged['Heave_m'], color='#B22222', label='Heave Response', linewidth=1.5)
            ax1b.set_xlabel('Time (s)')
            ax1b.set_ylabel('Elevation (m)')
            ax1b.grid(visible=True, linestyle='--', color='lightgray', alpha=0.7)
            ax1b.legend(loc='upper right')
            plt.title(f'Buoy Heave vs Wave Elevation (Single Y-Axis)\n{condition_text}', fontsize=12, fontweight='bold')
            fig1b.tight_layout()
            st.pyplot(fig1b)

            # กราฟ 2: Tension
            fig2, ax3 = plt.subplots(figsize=(10, 4))
            fig2.patch.set_facecolor('white')
            ax3.set_facecolor('white')
            ax3.plot(df_merged['Time_s'], df_merged['Tension_kN'], color='#800000', linewidth=1.5)
            ax3.set_xlabel('Time (s)')
            ax3.set_ylabel('Tension (kN)')
            ax3.set_title(f'Mooring Line Tension\n{condition_text}', fontsize=12, fontweight='bold')
            ax3.grid(visible=True, linestyle='--', color='lightgray', alpha=0.7)
            fig2.tight_layout()
            st.pyplot(fig2)

            # กราฟ 3: Rotation (รวม)
            fig3, ax4 = plt.subplots(figsize=(10, 4))
            fig3.patch.set_facecolor('white')
            ax4.set_facecolor('white')
            ax4.plot(df_merged['Time_s'], df_merged['RX_deg'], color='#FF8C00', label='RX (Roll)', linewidth=1.2)
            ax4.plot(df_merged['Time_s'], df_merged['RY_deg'], color='#2E8B57', label='RY (Pitch)', linewidth=1.2)
            ax4.plot(df_merged['Time_s'], df_merged['RZ_deg'], color='#8A2BE2', label='RZ (Yaw)', linewidth=1.2)
            ax4.set_xlabel('Time (s)')
            ax4.set_ylabel('Rotation (deg)')
            ax4.set_title(f'Rotational Response (Combined 3-Axes)\n{condition_text}', fontsize=12, fontweight='bold')
            ax4.grid(visible=True, linestyle='--', color='lightgray', alpha=0.7)
            ax4.legend(loc='upper right')
            fig3.tight_layout()
            st.pyplot(fig3)

            # กราฟ 4: RX & RY (คู่กัน)
            fig_rxry, ax_rxry = plt.subplots(figsize=(10, 4))
            fig_rxry.patch.set_facecolor('white')
            ax_rxry.set_facecolor('white')
            ax_rxry.plot(df_merged['Time_s'], df_merged['RX_deg'], color='#FF8C00', label='RX (Roll)', linewidth=1.5)
            ax_rxry.plot(df_merged['Time_s'], df_merged['RY_deg'], color='#2E8B57', label='RY (Pitch)', linewidth=1.5)
            ax_rxry.set_xlabel('Time (s)')
            ax_rxry.set_ylabel('Rotation (deg)')
            ax_rxry.set_title(f'Rotational Response: RX vs RY\n{condition_text}', fontsize=12, fontweight='bold')
            ax_rxry.grid(visible=True, linestyle='--', color='lightgray', alpha=0.7)
            ax_rxry.legend(loc='upper right')
            fig_rxry.tight_layout()
            st.pyplot(fig_rxry)

            # กราฟ 5: Rotation (แยก 3 แกน)
            st.markdown("##### กราฟแยกทีละแกน (Separated Axes)")
            fig4, (ax_rx, ax_ry, ax_rz) = plt.subplots(3, 1, figsize=(10, 8), sharex=True)
            fig4.patch.set_facecolor('white')
            
            ax_rx.plot(df_merged['Time_s'], df_merged['RX_deg'], color='#FF8C00', linewidth=1.5)
            ax_rx.set_ylabel('RX (deg)', color='#FF8C00')
            ax_rx.set_title(f'Rotational Response (Separated)\n{condition_text}', fontsize=12, fontweight='bold')
            ax_rx.grid(True, linestyle='--', color='lightgray', alpha=0.7)

            ax_ry.plot(df_merged['Time_s'], df_merged['RY_deg'], color='#2E8B57', linewidth=1.5)
            ax_ry.set_ylabel('RY (deg)', color='#2E8B57')
            ax_ry.grid(True, linestyle='--', color='lightgray', alpha=0.7)

            ax_rz.plot(df_merged['Time_s'], df_merged['RZ_deg'], color='#8A2BE2', linewidth=1.5)
            ax_rz.set_xlabel('Time (s)')
            ax_rz.set_ylabel('RZ (deg)', color='#8A2BE2')
            ax_rz.grid(True, linestyle='--', color='lightgray', alpha=0.7)
            
            fig4.tight_layout()
            st.pyplot(fig4)

            # ==========================================
            # ส่งออก Excel
            # ==========================================
            st.markdown("---")
            st.subheader("📥 ส่งออกข้อมูล (Export to Excel)")
            
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df_merged.to_excel(writer, sheet_name=sheet_data, index=False)
                workbook = writer.book
                worksheet_summary = workbook.add_worksheet(sheet_plot)
                worksheet_summary.set_column('A:C', 20)
                max_row = len(df_merged)

                # ดึงตำแหน่ง Index ของแต่ละคอลัมน์ให้ถูกต้องชัวร์ๆ
                col_time = df_merged.columns.get_loc('Time_s')
                col_wave = df_merged.columns.get_loc('Wave_m')
                col_heave = df_merged.columns.get_loc('Heave_m')
                col_tension = df_merged.columns.get_loc('Tension_kN')
                col_rx = df_merged.columns.get_loc('RX_deg')
                col_ry = df_merged.columns.get_loc('RY_deg')
                col_rz = df_merged.columns.get_loc('RZ_deg')

                def create_excel_chart(title, y_name, data_cols, colors, y_num_format='0.0'):
                    chart = workbook.add_chart({'type': 'line'})
                    for idx, col_index in enumerate(data_cols):
                        chart.add_series({
                            'name':       [sheet_data, 0, col_index],
                            'categories': [sheet_data, 1, col_time, max_row, col_time],
                            'values':     [sheet_data, 1, col_index, max_row, col_index],
                            'line':       {'color': colors[idx], 'width': 1.5}
                        })
                    chart.set_title({'name': title})
                    chart.set_x_axis({'name': 'Time (s)', 'label_position': 'low', 'num_format': '0.0', 'major_gridlines': {'visible': True, 'line': {'color': '#D9D9D9'}}})
                    chart.set_y_axis({'name': y_name, 'num_format': y_num_format, 'major_gridlines': {'visible': True, 'line': {'color': '#D9D9D9'}}})
                    chart.set_plotarea({'fill': {'none': True}})
                    chart.set_size({'width': 800, 'height': 300})
                    return chart

                # 1A. Wave & Heave (Dual Axis)
                chart1 = workbook.add_chart({'type': 'line'})
                chart1.add_series({
                    'name': [sheet_data, 0, col_wave], 
                    'categories': [sheet_data, 1, col_time, max_row, col_time], 
                    'values': [sheet_data, 1, col_wave, max_row, col_wave], 
                    'line': {'color': '#4169E1', 'width': 1.5}
                })
                chart1.add_series({
                    'name': [sheet_data, 0, col_heave], 
                    'categories': [sheet_data, 1, col_time, max_row, col_time], 
                    'values': [sheet_data, 1, col_heave, max_row, col_heave], 
                    'y2_axis': True, 
                    'line': {'color': '#B22222', 'width': 1.5}
                })
                chart1.set_title({'name': f'Buoy Heave vs Wave Elevation (Dual Axis)\n{condition_text}'})
                chart1.set_x_axis({'name': 'Time (s)', 'label_position': 'low', 'num_format': '0.0', 'major_gridlines': {'visible': True, 'line': {'color': '#D9D9D9'}}})
                chart1.set_y_axis({'name': 'Wave Elevation (m)', 'num_format': '0.0', 'min': wave_min_limit, 'max': wave_max_limit, 'major_gridlines': {'visible': True, 'line': {'color': '#D9D9D9'}}})
                chart1.set_y2_axis({'name': 'Heave Response (m)', 'num_format': '0.0', 'min': heave_min_limit, 'max': heave_max_limit})
                chart1.set_plotarea({'fill': {'none': True}})
                chart1.set_size({'width': 800, 'height': 350})
                worksheet_summary.insert_chart('B2', chart1)

                # 1B. Wave & Heave (Single Axis)
                chart1b = create_excel_chart(f'Buoy Heave vs Wave Elevation (Single Axis)\n{condition_text}', 'Elevation (m)', [col_wave, col_heave], ['#4169E1', '#B22222'], y_num_format='0.0')
                chart1b.set_legend({'position': 'top'})
                chart1b.set_size({'width': 800, 'height': 350})
                worksheet_summary.insert_chart('B20', chart1b)

                # 2. Tension
                chart2 = create_excel_chart(f'Mooring Line Tension Analysis\n{condition_text}', 'Mooring Tension (kN)', [col_tension], ['#800000'], y_num_format='0.0')
                chart2.set_legend({'position': 'none'})
                worksheet_summary.insert_chart('B38', chart2)

                # 3. Rotation (รวม 3 แกน)
                chart3 = create_excel_chart(f'Rotational Response (Combined)\n{condition_text}', 'Rotation (deg)', [col_rx, col_ry, col_rz], ['#FF8C00', '#2E8B57', '#8A2BE2'], y_num_format='0.0')
                worksheet_summary.insert_chart('B56', chart3)

                # 4. RX & RY (คู่กัน)
                chart_rxry = create_excel_chart(f'Rotational Response (RX & RY)\n{condition_text}', 'Rotation (deg)', [col_rx, col_ry], ['#FF8C00', '#2E8B57'], y_num_format='0.0')
                worksheet_summary.insert_chart('B74', chart_rxry)

                # 5. แยก RX
                chart_rx = create_excel_chart(f'RX (Roll) Response', 'RX (deg)', [col_rx], ['#FF8C00'], y_num_format='0.0')
                chart_rx.set_legend({'position': 'none'})
                worksheet_summary.insert_chart('B92', chart_rx)

                # 6. แยก RY
                chart_ry = create_excel_chart(f'RY (Pitch) Response', 'RY (deg)', [col_ry], ['#2E8B57'], y_num_format='0.0')
                chart_ry.set_legend({'position': 'none'})
                worksheet_summary.insert_chart('B110', chart_ry)

                # 7. แยก RZ
                chart_rz = create_excel_chart(f'RZ (Yaw) Response', 'RZ (deg)', [col_rz], ['#8A2BE2'], y_num_format='0.0')
                chart_rz.set_legend({'position': 'none'})
                worksheet_summary.insert_chart('B128', chart_rz)

            excel_data = output.getvalue()
            st.download_button(
                label="💾 Download All Plots Results (.xlsx)",
                data=excel_data,
                file_name=dl_filename, 
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                type="primary"
            )

    except Exception as e:
        st.error(f"เกิดข้อผิดพลาดในการประมวลผล: {e}")