#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""Windows 服务化支持 - 将打印服务注册为 Windows 系统服务

使用方法（需管理员权限）:
    安装服务:   python -m modules.win_service install
    启动服务:   python -m modules.win_service start
    停止服务:   python -m modules.win_service stop
    卸载服务:   python -m modules.win_service remove
    调试运行:   python -m modules.win_service debug

注意:
    - 安装/卸载操作需要以管理员身份运行
    - 服务启动后会在后台运行，无需用户登录
    - 服务默认自动启动（系统启动后）
"""

import os
import sys
import time
import threading

# 确保项目根目录在 sys.path 中
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

try:
    import win32serviceutil
    import win32service
    import win32event
    import servicemanager
    HAS_WIN32_SERVICE = True
except ImportError:
    HAS_WIN32_SERVICE = False

SERVICE_NAME = 'LANPrintService'
SERVICE_DISPLAY_NAME = '内网打印及扫描服务'
SERVICE_DESCRIPTION = (
    '提供局域网内的打印和扫描服务，'
    '支持Web界面访问、文件上传打印、扫描仪操作等功能。'
)


class PrintService(win32serviceutil.ServiceFramework if HAS_WIN32_SERVICE else object):
    """Windows 服务类"""

    if HAS_WIN32_SERVICE:
        _svc_name_ = SERVICE_NAME
        _svc_display_name_ = SERVICE_DISPLAY_NAME
        _svc_description_ = SERVICE_DESCRIPTION
        _svc_deps_ = None  # 无依赖服务

        def __init__(self, args):
            win32serviceutil.ServiceFramework.__init__(self, args)
            self.stop_event = win32event.CreateEvent(None, 0, 0, None)
            self.running = False

        def SvcStop(self):
            """服务停止回调"""
            self.running = False
            self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
            win32event.SetEvent(self.stop_event)
            servicemanager.LogMsg(servicemanager.EVENTLOG_INFORMATIONTYPE,
                                  servicemanager.PYS_SERVICE_STOPPED,
                                  (SERVICE_NAME, ''))

        def SvcDoRun(self):
            """服务启动回调"""
            self.running = True
            servicemanager.LogMsg(servicemanager.EVENTLOG_INFORMATIONTYPE,
                                  servicemanager.PYS_SERVICE_STARTED,
                                  (SERVICE_NAME, ''))
            self.main()

        def main(self):
            """服务主逻辑"""
            try:
                # 切换到项目目录
                os.chdir(_project_root)

                # 导入并初始化应用
                from modules import config
                from modules.config import init_paths, setup_logger
                from modules.path_manager import path_manager

                init_paths(path_manager)
                setup_logger(path_manager)
                config.logger.info(f"Windows 服务启动: {SERVICE_NAME}")

                # 导入 Flask 应用
                from app import app
                from modules.service_manager import service_manager, run_flask, run_wsgi
                from modules.file_manager import clean_old_files

                # 启动清理线程
                cleaner = threading.Thread(
                    target=clean_old_files, args=(path_manager, service_manager), daemon=True)
                cleaner.start()

                # 记录启动时间
                service_manager.start_time = time.time()

                # 启动 Web 服务
                port = config.get_config_port()
                app.current_port = port

                if os.environ.get('USE_WSGI', '').lower() == 'true':
                    server_thread = threading.Thread(target=run_wsgi, daemon=True)
                else:
                    server_thread = threading.Thread(target=run_flask, daemon=True)
                server_thread.start()

                config.logger.info(f"Windows 服务已就绪，端口: {port}")

                # 等待停止信号
                while self.running:
                    rc = win32event.WaitForSingleObject(self.stop_event, 5000)
                    if rc == win32event.WAIT_OBJECT_0:
                        break

                # 清理退出
                config.logger.info("Windows 服务正在停止...")
                service_manager.mark_service_stopped()

            except Exception as e:
                try:
                    servicemanager.LogErrorMsg(f"{SERVICE_NAME} 启动失败: {e}")
                except Exception:
                    pass


def install_service():
    """安装 Windows 服务"""
    if not HAS_WIN32_SERVICE:
        print("错误: 缺少 pywin32 服务模块，请运行: pip install pywin32")
        return False

    python_path = sys.executable
    script_path = os.path.abspath(__file__)

    # 使用 nssm 或 sc.exe 安装服务
    try:
        # 尝试用 win32serviceutil 安装
        win32serviceutil.InstallService(PrintService, SERVICE_NAME,
                                        SERVICE_DISPLAY_NAME,
                                        startType=win32service.SERVICE_AUTO_START)
        # 设置服务描述
        import winreg
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                             f"SYSTEM\\CurrentControlSet\\Services\\{SERVICE_NAME}",
                             access=winreg.KEY_SET_VALUE)
        winreg.SetValueEx(key, "Description", 0, winreg.REG_SZ, SERVICE_DESCRIPTION)
        winreg.CloseKey(key)

        print(f"服务 '{SERVICE_DISPLAY_NAME}' 已安装成功！")
        print(f"  服务名称: {SERVICE_NAME}")
        print(f"  启动方式: 自动启动")
        print(f"  启动命令: net start {SERVICE_NAME}")
        print(f"  停止命令: net stop {SERVICE_NAME}")
        print(f"  卸载命令: python -m modules.win_service remove")
        return True

    except Exception as e:
        print(f"服务安装失败: {e}")
        print("请确保以管理员身份运行此命令")
        return False


def remove_service():
    """卸载 Windows 服务"""
    if not HAS_WIN32_SERVICE:
        print("错误: 缺少 pywin32 服务模块")
        return False
    try:
        win32serviceutil.RemoveService(SERVICE_NAME)
        print(f"服务 '{SERVICE_DISPLAY_NAME}' 已卸载")
        return True
    except Exception as e:
        print(f"服务卸载失败: {e}")
        print("请确保以管理员身份运行此命令")
        return False


def start_service():
    """启动服务"""
    try:
        win32serviceutil.StartService(SERVICE_NAME)
        print(f"服务 '{SERVICE_DISPLAY_NAME}' 已启动")
        return True
    except Exception as e:
        print(f"服务启动失败: {e}")
        return False


def stop_service():
    """停止服务"""
    try:
        win32serviceutil.StopService(SERVICE_NAME)
        print(f"服务 '{SERVICE_DISPLAY_NAME}' 已停止")
        return True
    except Exception as e:
        print(f"服务停止失败: {e}")
        return False


def debug_service():
    """调试模式运行服务（不注册为系统服务）"""
    print(f"以调试模式运行 '{SERVICE_DISPLAY_NAME}'...")
    print("按 Ctrl+C 停止")

    os.chdir(_project_root)

    from modules import config
    from modules.config import init_paths, setup_logger
    from modules.path_manager import path_manager

    init_paths(path_manager)
    setup_logger(path_manager)

    from app import app
    from modules.service_manager import service_manager, run_flask
    from modules.file_manager import clean_old_files

    cleaner = threading.Thread(
        target=clean_old_files, args=(path_manager, service_manager), daemon=True)
    cleaner.start()

    service_manager.start_time = time.time()
    port = config.get_config_port()
    app.current_port = port

    server_thread = threading.Thread(target=run_flask, daemon=True)
    server_thread.start()

    print(f"服务运行中，端口: {port}")
    print(f"访问地址: http://127.0.0.1:{port}")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n正在停止...")
        service_manager.mark_service_stopped()
        print("已停止")


def main():
    """命令行入口"""
    if not HAS_WIN32_SERVICE:
        print("错误: 需要安装 pywin32 以使用 Windows 服务功能")
        print("安装命令: pip install pywin32")
        print("安装后运行: python Scripts/pywin32_postinstall.py -install")
        sys.exit(1)

    if len(sys.argv) < 2:
        print(f"Windows 服务管理 - {SERVICE_DISPLAY_NAME}")
        print()
        print("用法:")
        print(f"  python -m modules.win_service install    安装服务（自动启动）")
        print(f"  python -m modules.win_service remove     卸载服务")
        print(f"  python -m modules.win_service start      启动服务")
        print(f"  python -m modules.win_service stop       停止服务")
        print(f"  python -m modules.win_service debug      调试模式运行")
        print(f"  python -m modules.win_service status     查看服务状态")
        return

    cmd = sys.argv[1].lower()

    if cmd == 'install':
        install_service()
    elif cmd == 'remove':
        remove_service()
    elif cmd == 'start':
        start_service()
    elif cmd == 'stop':
        stop_service()
    elif cmd == 'debug':
        debug_service()
    elif cmd == 'status':
        try:
            status = win32serviceutil.QueryServiceStatus(SERVICE_NAME)
            state = status[1]
            states = {
                win32service.SERVICE_STOPPED: '已停止',
                win32service.SERVICE_START_PENDING: '正在启动',
                win32service.SERVICE_STOP_PENDING: '正在停止',
                win32service.SERVICE_RUNNING: '运行中',
                win32service.SERVICE_CONTINUE_PENDING: '正在继续',
                win32service.SERVICE_PAUSE_PENDING: '正在暂停',
                win32service.SERVICE_PAUSED: '已暂停',
            }
            print(f"服务 '{SERVICE_DISPLAY_NAME}' 状态: {states.get(state, f'未知({state})')}")
        except Exception as e:
            print(f"服务未安装或查询失败: {e}")
    else:
        # 传递给 win32serviceutil 处理（支持标准 Windows 服务命令）
        win32serviceutil.HandleCommandLine(PrintService)


if __name__ == '__main__':
    main()
