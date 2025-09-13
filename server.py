from flask import Flask, request, render_template, request as flask_request
import win32print
import os
import tempfile
import subprocess

app = Flask(__name__)
UPLOAD_FOLDER = tempfile.gettempdir()

@app.route('/', methods=['GET'])
def index():
    # 获取本机打印机列表
    try:
        printers = [p[2] for p in win32print.EnumPrinters(2)]
    except Exception:
        printers = []
    user_ip = flask_request.remote_addr
    return render_template('index.html', printers=printers, user_ip=user_ip)

@app.route('/print', methods=['POST'])
def print_file():
    file = request.files.get('file')
    copies = request.form.get('copies', 1, type=int)
    printer = request.form.get('printer', '')
    paper_size = request.form.get('paper_size', 'A4')
    # 纸张类型映射（win32print常用ID）
    paper_map = {
        'A4': 9, 'A3': 8, 'A5': 11, 'A6': 70, 'B5': 13, 'B6': 88, '16K': 124, 'Postcard': 75, 'Envelope': 37,
        'Letter': 1, 'Legal': 5, 'Executive': 7
    }
    paper_id = paper_map.get(paper_size, 9)
    # 获取本机打印机列表
    try:
        printers = [p[2] for p in win32print.EnumPrinters(2)]
    except Exception:
        printers = []
    user_ip = flask_request.remote_addr
    if not file:
        return render_template('index.html', msg="未选择文件！", printers=printers, user_ip=user_ip)
    # 保存文件到临时目录
    file_path = os.path.join(UPLOAD_FOLDER, file.filename)
    file.save(file_path)
    ext = file.filename.lower().split('.')[-1]
    if os.name == 'nt':  # Windows
        for _ in range(copies):
            if ext in ['txt', 'jpg', 'jpeg', 'png', 'bmp']:
                # 用win32print直接打印，设置纸张
                try:
                    hprinter = win32print.OpenPrinter(printer if printer else win32print.GetDefaultPrinter())
                    pdc = win32print.StartDocPrinter(hprinter, 1, (file.filename, None, "RAW"))
                    win32print.StartPagePrinter(hprinter)
                    with open(file_path, 'rb') as f:
                        data = f.read()
                        win32print.WritePrinter(hprinter, data)
                    win32print.EndPagePrinter(hprinter)
                    win32print.EndDocPrinter(hprinter)
                    win32print.ClosePrinter(hprinter)
                except Exception as e:
                    return render_template('index.html', msg=f"打印失败: {e}", printers=printers, user_ip=user_ip)
            elif ext == 'pdf':
                # SumatraPDF/Adobe Reader命令行暂不支持纸张参数，依赖默认设置
                sumatra = r'C:\Program Files\SumatraPDF\SumatraPDF.exe'
                acroread = r'C:\Program Files (x86)\Adobe\Acrobat Reader DC\Reader\AcroRd32.exe'
                if os.path.exists(sumatra):
                    cmd = [sumatra, '-print-to-default' if not printer else f'-print-to \\"{printer}\\"', file_path]
                    subprocess.run(cmd, shell=True)
                elif os.path.exists(acroread):
                    cmd = [acroread, '/t', file_path]
                    if printer:
                        cmd += [printer]
                    subprocess.run(cmd, shell=True)
                else:
                    return render_template('index.html', msg="未检测到PDF打印软件，请安装SumatraPDF或Adobe Reader！", printers=printers, user_ip=user_ip)
            else:
                subprocess.run(['print', file_path], shell=True)
    else:
        # Linux/Mac
        cmd = ['lp']
        if printer:
            cmd += ['-d', printer]
        cmd += ['-n', str(copies), file_path]
        subprocess.run(cmd)
    os.remove(file_path)
    return render_template('index.html', msg="文件已提交打印！", printers=printers, user_ip=user_ip)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
