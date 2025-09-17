#!/usr/bin/env python
# -*- coding: utf-8 -*-
 
import os
from flask import Flask, request, render_template_string, send_from_directory, redirect, url_for
# 打印相关
import win32print
import win32api
import subprocess
from datetime import datetime
# 托盘相关
 
 
 
import threading
import sys
import pystray
from PIL import Image
import socket
import winreg
import time
def clean_old_files(folder=None, expire_seconds=3600):
    """定期清理指定目录下超过expire_seconds的文件"""
    if folder is None:
        folder = UPLOAD_FOLDER
    while True:
        now = time.time()
        for fname in os.listdir(folder):
            fpath = os.path.join(folder, fname)
            if os.path.isfile(fpath):
                try:
                    if now - os.path.getmtime(fpath) > expire_seconds:
                        os.remove(fpath)
                except Exception:
                    pass
        time.sleep(600)  # 每10分钟检查一次
 
# 兼容PyInstaller打包和源码运行的资源路径
def resource_path(relative_path):
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)
 
# 获取本机局域网IP
def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return '127.0.0.1'
 
# 开机自启注册表操作
def set_autostart(enable=True):
    exe_path = sys.executable
    key = r'Software\\Microsoft\\Windows\\CurrentVersion\\Run'
    name = 'PrintServerApp'
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key, 0, winreg.KEY_ALL_ACCESS) as regkey:
        if enable:
            winreg.SetValueEx(regkey, name, 0, winreg.REG_SZ, exe_path)
        else:
            try:
                winreg.DeleteValue(regkey, name)
            except FileNotFoundError:
                pass
 
def get_autostart():
    key = r'Software\\Microsoft\\Windows\\CurrentVersion\\Run'
    name = 'PrintServerApp'
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key, 0, winreg.KEY_READ) as regkey:
            val, _ = winreg.QueryValueEx(regkey, name)
            return True if val else False
    except FileNotFoundError:
        return False
 
app = Flask(__name__)
UPLOAD_FOLDER = 'uploads'
LOG_FILE = 'print_log.txt'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
 
# 获取所有本地打印机
PRINTERS = [p[2] for p in win32print.EnumPrinters(2)]
 
HTML = '''
<!doctype html>
<html lang="zh-cn">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>内网打印服务</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        body { background: #f8f9fa; }
        .container { max-width: 700px; margin-top: 40px; background: #fff; border-radius: 12px; box-shadow: 0 2px 12px #0001; padding: 32px; }
        h1 { font-size: 2rem; margin-bottom: 1.5rem; }
        .form-label { font-weight: 500; }
        .table { background: #fff; }
        .log-list { max-height: 200px; overflow-y: auto; font-size: 0.95em; }
    </style>
</head>
<body>
<div class="container">
    <h1 class="mb-4 text-center">内网打印服务（作者：忆痕）</h1>
    <form method="post" enctype="multipart/form-data" class="row g-3 mb-4">
        <div class="col-md-6">
            <label class="form-label">选择打印机</label>
            <select name="printer" class="form-select">
                {% for p in printers %}
                    <option value="{{p}}">{{p}}</option>
                {% endfor %}
            </select>
        </div>
        <div class="col-md-3">
            <label class="form-label">打印份数</label>
            <input type="number" name="copies" value="1" min="1" max="10" class="form-control">
        </div>
        <div class="col-md-3">
            <label class="form-label">单双面</label>
            <select name="duplex" class="form-select">
                <option value="1">单面</option>
                <option value="2">长边翻转双面</option>
                <option value="3">短边翻转双面</option>
            </select>
        </div>
        <div class="col-md-4">
            <label class="form-label">纸张大小</label>
            <input type="text" name="papersize" value="A4" class="form-control">
        </div>
        <div class="col-md-4">
            <label class="form-label">纸张质量</label>
            <select name="quality" class="form-select">
                <option value="normal">普通</option>
                <option value="high">高质量</option>
                <option value="photo">相片纸</option>
            </select>
        </div>
        <div class="col-md-8">
            <label class="form-label">选择文件（支持PDF/JPG/PNG/TXT，支持多选）</label>
            <input type="file" name="file" multiple class="form-control">
        </div>
        <div class="col-12 text-end">
            <button type="submit" class="btn btn-primary px-4">上传并打印</button>
        </div>
    </form>
 
    <h4 class="mt-4">打印队列</h4>
    <table class="table table-sm table-hover align-middle">
        <thead class="table-light"><tr><th>文件名</th><th>操作</th></tr></thead>
        <tbody>
        {% for f in files %}
            <tr>
                <td>{{f}}</td>
                <td><a href="/preview/{{f}}" target="_blank" class="btn btn-outline-secondary btn-sm">预览</a></td>
            </tr>
        {% endfor %}
        </tbody>
    </table>
 
    <h4 class="mt-4">打印日志</h4>
    <ul class="list-group log-list mb-0">
        {% for l in logs %}
            <li class="list-group-item">{{l}}</li>
        {% endfor %}
    </ul>
</div>
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
'''
 
# 允许的文件类型
ALLOWED_EXT = {'pdf', 'jpg', 'jpeg', 'png', 'txt'}
 
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXT
 
## PDF 也用 Windows 系统自带打印
 
def log_print(filename, printer, copies, duplex, papersize, quality):
    with open(LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(f"{datetime.now()} 打印: {filename} 打印机: {printer} 份数: {copies} 双面: {duplex} 纸张: {papersize} 质量: {quality}\n")
 
def get_logs():
    if not os.path.exists(LOG_FILE):
        return []
    with open(LOG_FILE, 'r', encoding='utf-8') as f:
        return f.readlines()[-10:][::-1]
 
@app.route('/', methods=['GET', 'POST'])
def upload_file():
    files = os.listdir(UPLOAD_FOLDER)
    logs = get_logs()
    if request.method == 'POST':
        printer = request.form.get('printer')
        copies = int(request.form.get('copies', 1))
        duplex = int(request.form.get('duplex', 1))
        papersize = request.form.get('papersize', 'A4')
        quality = request.form.get('quality', 'normal')
        uploaded_files = request.files.getlist('file')
         
        for f in uploaded_files:
            if f and allowed_file(f.filename):
                # 确保文件名唯一，避免覆盖
                filename = f.filename
                filepath = os.path.join(UPLOAD_FOLDER, filename)
                counter = 1
                while os.path.exists(filepath):
                    name, ext = os.path.splitext(filename)
                    filepath = os.path.join(UPLOAD_FOLDER, f"{name}_{counter}{ext}")
                    counter += 1
                 
                # 保存文件到uploads文件夹
                f.save(filepath)
                ext = os.path.splitext(filepath)[1][1:].lower()
                 
                try:
                    if ext in {'txt', 'jpg', 'jpeg', 'png'}:
                        # 使用win32print设置正确的打印机和参数
                        hprinter = win32print.OpenPrinter(printer)
                        pdc = win32print.GetPrinter(hprinter, 2)
                        devmode = pdc['pDevMode']
                         
                        # 设置打印质量
                        if quality == 'high':
                            devmode.PrintQuality = -4  # DMRES_HIGH
                        elif quality == 'photo':
                            devmode.PrintQuality = 1200  # 1200dpi，部分驱动支持
                        else:
                            devmode.PrintQuality = -3  # DMRES_DRAFT/普通
                         
                        # 设置双面打印
                        if hasattr(devmode, 'Duplex'):
                            devmode.Duplex = duplex  # 1=单面, 2=长边翻转, 3=短边翻转
                         
                        # 更新打印机设置
                        pdc['pDevMode'] = devmode
                        win32print.SetPrinter(hprinter, 2, pdc, 0)
                         
                        for _ in range(copies):
                            hjob = win32print.StartDocPrinter(hprinter, 1, (os.path.basename(filepath), None, "RAW"))
                            win32print.StartPagePrinter(hprinter)
                            with open(filepath, 'rb') as file_data:
                                win32print.WritePrinter(hprinter, file_data.read())
                            win32print.EndPagePrinter(hprinter)
                            win32print.EndDocPrinter(hprinter)
                        win32print.ClosePrinter(hprinter)
                    else:
                        # 对于PDF文件，使用正确的命令行方式打印到指定打印机
                        # 检查系统是否安装了Acrobat Reader或其他PDF查看器
                        pdf_viewers = [
                            r"C:\Program Files (x86)\Adobe\Acrobat Reader DC\Reader\AcroRd32.exe",
                            r"C:\Program Files\Adobe\Acrobat Reader DC\Reader\AcroRd32.exe",
                            r"C:\Program Files\Adobe\Acrobat DC\Acrobat\Acrobat.exe"
                        ]
                         
                        pdf_viewer = None
                        for viewer in pdf_viewers:
                            if os.path.exists(viewer):
                                pdf_viewer = viewer
                                break
                         
                        if pdf_viewer:
                            # 使用Adobe Reader命令行打印
                            for _ in range(copies):
                                subprocess.run([
                                    pdf_viewer,
                                    "/t", filepath, printer
                                ], shell=False, check=True)
                        else:
                            # 回退到Windows默认打印方式
                            print_cmd = f'Shell.Print "{filepath}" /d:"{printer}"' if sys.platform == 'win32' else f'lpr -P "{printer}" "{filepath}"'
                            subprocess.run(f'powershell -Command "{print_cmd}"', shell=True, check=True)
                     
                    log_print(os.path.basename(filepath), printer, copies, duplex, papersize, quality)
                except Exception as e:
                    error_msg = f"打印失败: {str(e)}"
                    log_print(os.path.basename(filepath) + " " + error_msg, printer, copies, duplex, papersize, quality)
                    # 可以考虑添加flash消息来显示错误
         
        return redirect(url_for('upload_file'))
    return render_template_string(HTML, printers=PRINTERS, files=files, logs=logs)
 
@app.route('/preview/<filename>')
def preview_file(filename):
    ext = filename.rsplit('.', 1)[1].lower()
    if ext in {'jpg', 'jpeg', 'png'}:
        return send_from_directory(UPLOAD_FOLDER, filename)
    elif ext == 'pdf':
        return send_from_directory(UPLOAD_FOLDER, filename)
    elif ext == 'txt':
        with open(os.path.join(UPLOAD_FOLDER, filename), 'r', encoding='utf-8') as f:
            return f'<pre>{f.read()}</pre>'
    else:
        return '不支持预览'
 
 
def run_flask():
    app.run(host='0.0.0.0', port=5000)
 
 
def on_quit(icon, item):
    icon.stop()
    os._exit(0)
 
def on_toggle_autostart(icon, item):
    current = get_autostart()
    set_autostart(not current)
    # 刷新菜单
    icon.menu = build_menu(icon)
 
def build_menu(icon):
    autostart = get_autostart()
    ip = get_local_ip()
    port = 5000
    return pystray.Menu(
        pystray.MenuItem(f'服务地址: {ip}:{port}', None, enabled=False),
        pystray.MenuItem('开机自启：' + ('已开启' if autostart else '未开启'), on_toggle_autostart),
        pystray.MenuItem('退出', on_quit)
    )
 
def setup_tray():
    image = Image.open(resource_path('logo.ico'))
    icon = pystray.Icon('print_server', image, '内网打印服务')
    icon.menu = build_menu(icon)
    icon.run()
 
if __name__ == '__main__':
    # 启动定期清理线程
    cleaner_thread = threading.Thread(target=clean_old_files, daemon=True)
    cleaner_thread.start()
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    setup_tray()
