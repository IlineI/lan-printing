#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""程序启动器 - 初始化编排、控制台管理、异常诊断"""

import os
import sys
import time
import socket
import threading

from modules import config
from modules.config import get_config_port, init_paths
from modules.path_manager import path_manager
from modules.network import get_local_ip, get_external_ip, detect_network_mode
from modules.printer_manager import PRINTERS, get_default_printer
from modules.file_manager import clean_old_files
from modules.service_manager import service_manager, monitor_service_health, run_flask, run_wsgi
from modules.tray import (setup_tray, check_admin_privileges, check_windows_features,
                  show_error_dialog, auto_clear_console)


def launch(app):
    """主启动入口，由 app.py 的 __main__ 调用"""

    try:
        # 统一的控制台处理逻辑（所有 Windows 版本）
        if hasattr(sys, '_MEIPASS'):
            print(" 检测到exe文件运行模式")
            print(" 内网打印及扫描服务 by 忆痕")

        try:
            import ctypes
            import msvcrt

            kernel32 = ctypes.windll.kernel32
            user32 = ctypes.windll.user32

            console_window = kernel32.GetConsoleWindow()
            config.CONSOLE_WINDOW = console_window

            if console_window:
                print("\n按任意键可在5秒内保留控制台窗口，否则程序将隐藏控制台...")
                print("\n程序在托盘栏运行，右键程序图标，最上方第一个就是IP端口信息...")
                print("\n局域网下的其他设备可在浏览器地址栏里输入该IP端口，访问可视化网页，进行打印和扫描操作...")
                sys.stdout.flush()

                start = time.time()
                keep_console = False

                while time.time() - start < 5:
                    if msvcrt.kbhit():
                        _ = msvcrt.getch()
                        keep_console = True
                        print("\n已保留控制台窗口（用户按键）")
                        config.CONSOLE_VISIBLE = True
                        break
                    time.sleep(0.1)

                if not keep_console:
                    user32.ShowWindow(console_window, 0)
                    config.CONSOLE_VISIBLE = False

        except Exception as e:
            print(f"控制台处理异常: {e}")

        # 端口检测
        port = get_config_port()
        for arg in sys.argv:
            if arg.startswith('--port='):
                try:
                    cmdline_port = int(arg.split('=')[1])
                    port = cmdline_port
                    print(f"使用命令行指定端口: {port}")
                except ValueError:
                    print(f"警告: 无效的端口参数 {arg}，使用配置文件端口 {port}")

        app.current_port = port

        print("=" * 60)
        print("              内网打印及扫描服务")
        print("              作者：忆痕")
        print("    GitHub: https://github.com/a937750307/lan-printing")
        print("=" * 60)

        # 中文计算机名检测
        try:
            current_hostname = socket.gethostname()
            if any(ord(c) > 127 for c in current_hostname):
                print(f"   警告: 检测到中文计算机名!")
                print(f"   当前计算机名: {current_hostname}")
                print(f"   中文计算机名可能导致网络连接时名称解析错误")
                print(f"   建议改为英文名(例如: PrintServer-01)，重启电脑生效")
        except Exception as e:
            print(f" 计算机名检测异常: {e}")

        # 管理员权限检测
        is_admin = check_admin_privileges()
        if is_admin:
            print(" 当前运行模式: 管理员模式 (所有功能可用)")
        else:
            print(" 当前运行模式: 非管理员模式（部分功能受限）")
            print("  请关闭当前程序后，右键exe程序 → '以管理员身份运行' 重新运行以获得完整功能")

        # 路径信息
        print(f"程序目录: {path_manager.app_dir}")
        print(f"上传目录: {config.UPLOAD_FOLDER}")
        print(f"配置文件: {config.CONFIG_FILE}")
        print(f"日志文件: {config.LOG_FILE}")
        if hasattr(sys, '_MEIPASS'):
            print(f" 运行模式: PyInstaller打包 (资源目录: {sys._MEIPASS})")
        else:
            print(f" 运行模式: 源码运行")

        config_port = get_config_port()
        if port == config_port:
            print(f" 使用配置端口: {port}")
        else:
            print(f" 使用临时端口: {port} (配置端口: {config_port})")

        # 控制台窗口句柄
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            config.CONSOLE_WINDOW = kernel32.GetConsoleWindow()
            print(" 控制台控制功能已就绪")
        except:
            pass

        # 网络状态
        local_ip = get_local_ip()
        if local_ip == '127.0.0.1':
            print(" 网络状态: 离线模式")
            print("    本地打印功能完全正常，直接使用系统打印机")
            print(f"   本机访问: http://127.0.0.1:{port}")
        else:
            print(f" 网络状态: 在线 (IP: {local_ip})")
            print("      完整功能可用，支持网络打印机参数获取")

        # 打印机检测
        print(f"检测到 {len(PRINTERS)} 台物理打印机")
        if PRINTERS:
            for i, printer in enumerate(PRINTERS[:3], 1):
                print(f"   {i}. {printer}")
            if len(PRINTERS) > 3:
                print(f"   ... 还有 {len(PRINTERS) - 3} 台打印机")
        else:
            print("       未检测到可用的物理打印机")
            print("       程序仍可运行，但打印功能可能受限")
            print("       请检查: 打印机连接、驱动安装、Windows打印机和扫描仪设置")
            show_error_dialog(
                "打印机检测提示",
                "未检测到可用的物理打印机。\n\n"
                "请检查：\n"
                "• 打印机是否正确连接并开机\n"
                "• 打印机驱动程序是否已安装\n"
                "• Windows 设置 > 打印机和扫描仪中是否显示\n"
                "• 尝试重启程序或点击界面中的'刷新'按钮\n\n"
                "程序仍可正常运行，检测到打印机后即可使用。",
                is_critical=False
            )

        print("服务器将启动在: http://{}:{}".format(local_ip, port))
        print("=" * 60)

        # Windows功能检测
        issues, suggestions = check_windows_features()
        if issues:
            print(" 检测到以下问题：")
            for issue in issues:
                print(f"   - {issue}")
            print(" 建议解决方案：")
            for suggestion in suggestions:
                print(f"   - {suggestion}")

        # 端口占用检测
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.bind(('localhost', port))
            sock.close()
        except socket.error:
            error_msg = f"""端口 {port} 已被占用！

可能的原因：
• 该端口被其他程序占用
• 之前的程序实例未完全关闭
• 系统服务占用了该端口

解决方案：
1. 更换端口：python app.py --port=5001
2. 查找占用进程：netstat -ano | findstr :{port}
3. 结束占用进程：taskkill /PID [进程ID] /F
4. 重启计算机后再试"""
            show_error_dialog("端口占用错误", error_msg)
            sys.exit(1)

        # 启动定期清理线程
        service_manager.cleaner_thread = threading.Thread(
            target=clean_old_files, args=(path_manager, service_manager), daemon=True)
        service_manager.cleaner_thread.start()

        # 启动服务监控线程
        service_manager.monitor_thread = threading.Thread(target=monitor_service_health, daemon=True)
        service_manager.monitor_thread.start()
        print("【OK】服务监控线程已启动")

        # 启动控制台自动清理线程
        console_cleaner_thread = threading.Thread(target=auto_clear_console, daemon=True)
        console_cleaner_thread.start()
        print("【OK】控制台自动清理线程已启动")

        # 记录服务启动时间
        service_manager.start_time = time.time()

        # 启动Web服务
        if os.environ.get('USE_WSGI', '').lower() == 'true':
            service_manager.flask_thread = threading.Thread(target=run_wsgi, daemon=True)
        else:
            service_manager.flask_thread = threading.Thread(target=run_flask, daemon=True)
        service_manager.flask_thread.start()

        print("正在启动Web服务...")
        time.sleep(2)
        print("打印服务启动完成！")

        if local_ip == '127.0.0.1':
            print(" 离线模式已就绪")
            if len(PRINTERS) > 0:
                print(f"    本机访问: http://127.0.0.1:{port}")
                print(f"    可用打印机: {len(PRINTERS)} 台")
            else:
                print(f"   本机访问: http://127.0.0.1:{port}")
                print("    未检测到打印机，请检查打印机连接")
        else:
            print(" 在线模式已就绪")
            network_mode = detect_network_mode()
            external_ip = get_external_ip()
            print(f"   访问地址: http://{local_ip}:{port}")
            if len(PRINTERS) > 0:
                print(f"   可用打印机: {len(PRINTERS)} 台")
            else:
                print("   未检测到打印机，请检查打印机连接")
            if network_mode == "internal_tunnel" and external_ip:
                print("    局域网环境")
                print(f"      • 内网IP: {local_ip}")
                if external_ip:
                    print(f"      • 路由器公网IP: {external_ip}")
            elif network_mode == "public":
                print("    公网环境 - 外部可直接访问")
            else:
                print("    局域网环境")

        print("右键托盘图标查看更多功能")
        setup_tray()

    except KeyboardInterrupt:
        print("\n程序被用户中断 (Ctrl+C)，正在优雅退出...")
        try:
            service_manager.mark_service_stopped()
            service_manager.clear_restart()
            if service_manager.flask_thread and service_manager.flask_thread.is_alive():
                print("等待Web服务结束...")
                service_manager.flask_thread.join(timeout=1)
            print("【OK】优雅退出完成")
        except Exception as e:
            print(f"优雅退出失败: {e}")
        finally:
            os._exit(0)

    except Exception as e:
        _handle_fatal_error(e)


def _handle_fatal_error(e):
    """处理启动阶段的致命错误，显示诊断信息"""
    try:
        import platform
        import traceback

        system_info = {
            'system': platform.system(),
            'release': platform.release(),
            'version': platform.version(),
            'machine': platform.machine(),
            'processor': platform.processor(),
            'python_version': platform.python_version(),
        }

        win11_hints = []
        error_str = str(e).lower()
        if 'access' in error_str or 'permission' in error_str:
            win11_hints.append("权限问题：请以管理员身份运行程序")
        if 'import' in error_str or 'module' in error_str:
            win11_hints.append("依赖库缺失：程序打包可能不完整")
        if 'socket' in error_str or 'bind' in error_str:
            win11_hints.append("网络权限：检查防火墙和Windows Defender设置")
        if 'file' in error_str or 'path' in error_str:
            win11_hints.append("路径问题：避免中文路径，移动到英文目录")

        full_traceback = traceback.format_exc()

    except:
        system_info = {'error': '无法获取系统信息'}
        win11_hints = []
        full_traceback = str(e)

    error_msg = f"""程序启动时发生严重错误：

 错误信息: {str(e)}

️ 系统信息:
• 系统: {system_info.get('system', 'Unknown')} {system_info.get('release', 'Unknown')}
• Python: {system_info.get('python_version', 'Unknown')}
• 架构: {system_info.get('machine', 'Unknown')}

 Win11专用诊断:
""" + '\n'.join(f"• {hint}" for hint in win11_hints) + f"""

 解决方案：
1. 【立即尝试】右键程序图标 → "以管理员身份运行"
2. 【Win11专用】添加Windows Defender排除项
3. 【路径问题】移动程序到简单英文路径
4. 【网络问题】检查防火墙设置
5. 【依赖问题】重新下载完整版程序

 获取帮助：
• GitHub Issues: https://github.com/a937750307/lan-printing/issues

--- 技术详情 ---
{full_traceback}
"""

    show_error_dialog("程序启动失败", error_msg)
    print(f"\n严重错误: {e}")
    if win11_hints:
        print(f" Win11提示: {', '.join(win11_hints)}")
    print("\n--- 完整错误信息 ---")
    import traceback
    traceback.print_exc()
    sys.exit(1)
