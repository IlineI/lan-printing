如果想运行 server.py 文件，需要按照以下步骤操作：

安装 Python
确保已安装 Python 3.x（建议 3.7 及以上版本）。
我用的是Python 3.9.13

安装依赖库
需要安装 Flask 和 pywin32（包含 win32print），可以在命令行中运行：
```bash
pip install flask pywin32
```
准备打印软件（可选）
如果要支持 PDF 打印，建议安装 SumatraPDF 或 Adobe Reader，并确保路径与代码中一致。

准备模板文件
你的代码用到了 index.html，需要将该模板文件放在 templates 文件夹下（与 server.py 同级）。

运行程序
在命令行进入 server.py 所在目录，运行：
```bash
python server.py
```

访问服务
在浏览器中访问 http://本机IP:5000/ 即可使用。

注意事项：
需要在 Windows 系统下运行（因为用到了 win32print）。
需要有打印机驱动和权限。
若有防火墙，需允许 5000 端口访问。
