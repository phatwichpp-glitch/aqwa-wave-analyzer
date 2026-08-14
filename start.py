import sys
import subprocess

print("🚀 กำลังเปิด...")
print("รอสักครู่นะครับ หน้าเว็บจะเด้งขึ้นมาอัตโนมัติ...")

# ให้ Python ตัวที่ทำงานอยู่ ไปเรียก Streamlit ให้เปิดไฟล์ graph.py
subprocess.run([sys.executable, "-m", "streamlit", "run", "app.py"])