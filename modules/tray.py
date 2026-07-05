#!/usr/bin/env python
# -*- coding: utf-8 -*-
#作者：忆痕
#仓库地址：https://github.com/a937750307/lan-printing

"""系统托盘 - 图标、菜单、控制台控制、消息框"""

import os
import sys
import time
import json
import threading
import subprocess

from modules.config import (CONSOLE_WINDOW, CONSOLE_VISIBLE, DEBUG_MODE)
from modules import config
from modules.path_manager import path_manager
from modules.network import get_local_ip, get_current_ip_config, set_static_ip, set_dhcp
from modules.printer_manager import get_autostart, set_autostart
from modules.file_manager import clean_old_logs, clean_old_logs_by_date

try:
    import pystray
    from PIL import Image, ImageDraw
except ImportError:
    pass


def clear_console():
    """清理控制台内容"""
    try:
        if os.name == 'nt':
            os.system('cls')
    except:
        pass


def auto_clear_console():
    """定期自动清理控制台的后台任务"""
    while True:
        try:
            time.sleep(1800)
            if config.CONSOLE_VISIBLE:
                if os.name == 'nt':
                    from ctypes import windll, create_string_buffer
                    h = windll.kernel32.GetStdHandle(-11)
                    csbi = create_string_buffer(22)
                    windll.kernel32.GetConsoleScreenBufferInfo(h, csbi)
                    lines = csbi.raw[8] * 0x10000 | csbi.raw[9]
                    if lines > 1000:
                        clear_console()
        except:
            time.sleep(300)


def show_console():
    """显示控制台窗口"""
    try:
        import ctypes
        if not config.CONSOLE_WINDOW:
            config.CONSOLE_WINDOW = ctypes.windll.kernel32.GetConsoleWindow()
        if config.CONSOLE_WINDOW:
            ctypes.windll.user32.ShowWindow(config.CONSOLE_WINDOW, 1)
            ctypes.windll.user32.SetForegroundWindow(config.CONSOLE_WINDOW)
            config.CONSOLE_VISIBLE = True
    except:
        pass


def hide_console():
    """隐藏控制台窗口"""
    try:
        import ctypes
        if not config.CONSOLE_WINDOW:
            config.CONSOLE_WINDOW = ctypes.windll.kernel32.GetConsoleWindow()
        if config.CONSOLE_WINDOW:
            ctypes.windll.user32.ShowWindow(config.CONSOLE_WINDOW, 0)
            config.CONSOLE_VISIBLE = False
    except:
        pass


def toggle_console_window(icon, item):
    """切换控制台窗口显示/隐藏"""
    if config.CONSOLE_VISIBLE:
        hide_console()
    else:
        show_console()
    icon.menu = build_menu(icon)


def show_message_box(msg_type, title, message):
    """显示消息框 - 正确处理 Tkinter 窗口生命周期"""
    import tkinter as tk
    from tkinter import messagebox
    try:
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        root.update()
        result = None
        try:
            if msg_type == 'info':
                messagebox.showinfo(title, message, parent=root)
            elif msg_type == 'error':
                messagebox.showerror(title, message, parent=root)
            elif msg_type == 'warning':
                messagebox.showwarning(title, message, parent=root)
            elif msg_type == 'yesno':
                result = messagebox.askyesno(title, message, parent=root)
            elif msg_type == 'okcancel':
                result = messagebox.askokcancel(title, message, parent=root)
            else:
                messagebox.showinfo(title, message, parent=root)
        finally:
            try:
                root.destroy()
            except:
                pass
        return result
    except Exception as e:
        print(f"[{title}] {message}")
        if msg_type == 'yesno':
            return False
        return None


def show_error_dialog(title, message, is_critical=True):
    """显示友好的错误对话框"""
    try:
        import tkinter as tk
        from tkinter import messagebox
        root = tk.Tk()
        root.withdraw()
        if is_critical:
            messagebox.showerror(title, message)
        else:
            messagebox.showwarning(title, message)
        root.destroy()
        return True
    except Exception:
        print(f"\n{'='*50}\n错误: {title}\n{'='*50}\n{message}\n{'='*50}\n")
        return False


# ===== 托盘菜单回调函数 =====

def on_quit(icon, item):
    print(" 正在退出程序...")
    try:
        from modules.service_manager import service_manager
        service_manager.is_shutting_down = True
        service_manager.mark_service_stopped()
        service_manager.clear_restart()
        print(" 正在关闭Web服务...")
        try:
            from app import app
            if hasattr(app, 'shutdown'):
                app.shutdown()
        except Exception as e:
            print(f"关闭Flask服务时出错: {e}")
        print(" 正在等待服务线程结束...")
        threads_to_wait = []
        if service_manager.flask_thread and service_manager.flask_thread.is_alive():
            threads_to_wait.append(("Flask服务", service_manager.flask_thread))
        if service_manager.cleaner_thread and service_manager.cleaner_thread.is_alive():
            threads_to_wait.append(("文件清理", service_manager.cleaner_thread))
        if service_manager.monitor_thread and service_manager.monitor_thread.is_alive():
            threads_to_wait.append(("服务监控", service_manager.monitor_thread))
        for thread_name, thread in threads_to_wait:
            try:
                thread.join(timeout=2)
            except Exception as e:
                pass
        print(" 正在停止托盘图标...")
        icon.stop()
        print(" 程序退出准备完成")
    except Exception as e:
        print(f" 退出过程中出现错误: {e}")
    finally:
        try:
            os._exit(0)
        except Exception:
            sys.exit(0)


def on_show_ip_config(icon, item):
    """通过浏览器打开主页"""
    import webbrowser
    ip = get_local_ip()
    from app import app
    port = getattr(app, 'current_port', 5000)
    url = f"http://{ip}:{port}/"
    webbrowser.open(url)


def on_set_current_ip_static(icon, item):
    """将当前IP设置为静态IP"""
    try:
        current_ip = get_local_ip()
        if current_ip == '127.0.0.1':
            show_message_box("error", "无效IP", "当前IP为本地回环地址，无法设置为静态IP")
            return
        result = show_message_box(
            "yesno", "设置当前IP为静态",
            f"确认将当前IP设置为静态IP吗？\n\n"
            f"当前IP: {current_ip}\n"
            f"子网掩码: 255.255.255.0\n"
            f"网关: {'.'.join(current_ip.split('.')[:-1])}.1\n\n"
            f" 这将固定当前IP地址"
        )
        if result:
            success, message = set_static_ip(current_ip)
            if success:
                show_message_box("info", "设置成功", f"已将当前IP设置为静态IP\n\n静态IP: {current_ip}")
                def delayed_refresh():
                    time.sleep(5)
                    try:
                        icon.menu = build_menu(icon)
                    except:
                        pass
                threading.Thread(target=delayed_refresh, daemon=True).start()
            else:
                show_message_box("error", "设置失败", f"设置失败: {message}")
    except Exception as e:
        show_message_box("error", "错误", f"设置静态IP时发生错误: {str(e)}")


def on_enable_dhcp(icon, item):
    """启用DHCP"""
    try:
        success, message = set_dhcp()
        if success:
            show_message_box("info", "DHCP设置成功", f"{message}")
            def delayed_refresh():
                time.sleep(8)
                try:
                    icon.menu = build_menu(icon)
                except:
                    pass
            threading.Thread(target=delayed_refresh, daemon=True).start()
        else:
            show_message_box("error", "DHCP设置失败", message)
    except Exception as e:
        show_message_box("error", "错误", f"启用DHCP时发生错误: {str(e)}")


def on_open_github(icon, item):
    import webbrowser
    webbrowser.open("https://github.com/a937750307/lan-printing")


def on_donate(icon, item):
    try:
        import webbrowser
        webbrowser.open('https://zanzhu.937788.xyz/')
    except Exception as e:
        print(f"打开赞助页面失败: {e}")


def on_view_config(icon, item):
    try:
        from modules.config import load_config
        cfg = load_config()
        config_info = f"""当前配置信息：

端口设置: {cfg.get('port', 5000)} {'' if cfg.get('port') else '(默认)'}
配置文件: {config.CONFIG_FILE}

配置文件内容：
{json.dumps(cfg, ensure_ascii=False, indent=2) if cfg else '{}'}

说明：
• 端口设置保存后需要手动重新运行程序才能生效
• 配置文件保存在用户桌面目录  
• 可通过托盘菜单修改端口设置"""
        show_message_box("info", "配置信息", config_info)
    except Exception as e:
        show_message_box("error", "错误", f"查看配置时发生错误: {str(e)}")


def on_reset_config(icon, item):
    try:
        result = show_message_box(
            "yesno", "重置配置确认",
            "确定要重置所有配置到默认值吗？\n\n"
            "这将：\n• 将端口重置为 5000\n• 删除当前配置文件\n• 需要重启程序生效"
        )
        if result:
            if os.path.exists(config.CONFIG_FILE):
                os.remove(config.CONFIG_FILE)
                show_message_box("info", "重置成功", "配置已重置，程序将重启以应用默认设置")
                icon.stop()
                subprocess.Popen([sys.executable] + sys.argv)
                sys.exit(0)
            else:
                show_message_box("info", "提示", "配置文件不存在，当前已是默认配置")
    except Exception as e:
        pass


def on_change_port(icon, item):
    import tkinter as tk
    from tkinter import simpledialog
    try:
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        root.update()
        from app import app
        current_port = getattr(app, 'current_port', 5000)
        try:
            new_port = simpledialog.askinteger(
                "更改端口",
                f"当前端口: {current_port}\n请输入新的端口号 (1024-65535):",
                minvalue=1024, maxvalue=65535, initialvalue=current_port, parent=root
            )
        finally:
            try:
                root.destroy()
            except:
                pass
        if new_port and new_port != current_port:
            import socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                sock.bind(('localhost', new_port))
                sock.close()
                result = show_message_box(
                    "yesno", "端口更改确认",
                    f"将端口从 {current_port} 更改为 {new_port}\n\n"
                    f" 注意：更改端口后需要手动重新运行程序才能生效\n"
                    f"是否继续更改端口？"
                )
                if result:
                    from modules.config import save_port_config
                    if save_port_config(new_port):
                        show_message_box("info", "端口更改成功",
                                        f"端口已更改为: {new_port}\n新的访问地址: http://{get_local_ip()}:{new_port}")
                    else:
                        show_message_box("warning", "端口更改",
                                        f"端口已更改为: {new_port}，但配置保存失败")
                    icon.stop()
            except socket.error:
                show_message_box("error", "端口错误", f"端口 {new_port} 已被占用")
    except Exception as e:
        show_message_box("error", "错误", f"更改端口时发生错误: {str(e)}")


def on_clean_logs(icon, item):
    try:
        import tkinter as tk
        from tkinter import messagebox
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        root.update()
        try:
            result = messagebox.askyesnocancel(
                "清理日志确认",
                "选择日志清理方式：\n\n按大小(Y) - 保留最新1000条\n按日期(N) - 删除7天前的记录\n取消 - 不清理",
                parent=root
            )
        finally:
            try:
                root.destroy()
            except:
                pass
        if result is True:
            clean_old_logs()
            show_message_box("info", "清理完成", "已按大小清理日志")
        elif result is False:
            clean_old_logs_by_date()
            show_message_box("info", "清理完成", "已删除7天前的日志记录")
    except Exception as e:
        print(f"手动清理日志失败: {e}")


def on_view_log_info(icon, item):
    try:
        if os.path.exists(config.LOG_FILE):
            file_size = os.path.getsize(config.LOG_FILE)
            with open(config.LOG_FILE, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            size_mb = file_size / (1024 * 1024)
            first_date = "未知"
            last_date = "未知"
            try:
                if lines:
                    first_line = lines[0].strip()
                    if len(first_line) >= 19:
                        first_date = first_line[:19]
                    last_line = lines[-1].strip()
                    if len(last_line) >= 19:
                        last_date = last_line[:19]
            except:
                pass
            info = f""" 打印日志信息

 文件大小: {size_mb:.2f} MB
 记录总数: {len(lines)} 条
 最早记录: {first_date}
 最新记录: {last_date}
 文件路径: {config.LOG_FILE}"""
            import tkinter as tk
            from tkinter import messagebox
            root = tk.Tk()
            root.withdraw()
            messagebox.showinfo("日志信息", info)
            root.destroy()
        else:
            show_message_box("info", "日志信息", "日志文件不存在")
    except Exception as e:
        print(f"查看日志信息失败: {e}")


def on_clear_console(icon, item):
    if config.CONSOLE_VISIBLE:
        clear_console()


def on_open_qr_plugin(icon, item):
    try:
        import webbrowser
        webbrowser.open('https://ext.se.360.cn/webstore/detail/afpbjjgbdimpioenaedcjgkaigggcdpp')
    except Exception as e:
        print(f"打开二维码插件链接失败: {e}")


def on_open_upgrade(icon, item):
    try:
        import webbrowser
        webbrowser.open('https://print.937788.xyz/')
    except Exception as e:
        print(f"打开页面失败: {e}")


def on_toggle_autostart(icon, item):
    current = get_autostart()
    set_autostart(not current)
    icon.menu = build_menu(icon)


def build_menu(icon):
    from app import app
    from modules.config import get_config_port
    autostart = get_autostart()
    ip = get_local_ip()
    port = getattr(app, 'current_port', 5000)
    ip_config = get_current_ip_config()
    ip_status = f"当前IP: {ip}"
    if ip_config:
        if ip_config['dhcp_enabled']:
            ip_status += " (DHCP)"
        else:
            ip_status += " (静态)"
    config_port = get_config_port()
    port_status = f"当前端口: {port}"
    if port == config_port:
        port_status += " "
    else:
        port_status += " (临时)"
    return pystray.Menu(
        pystray.MenuItem(f'服务地址: {ip}:{port}', on_show_ip_config),
        pystray.MenuItem(ip_status, None, enabled=False),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem('网络配置（需要管理员权限）', pystray.Menu(
            pystray.MenuItem('设置当前IP为静态', on_set_current_ip_static),
            pystray.MenuItem('启用DHCP', on_enable_dhcp),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(port_status, None, enabled=False),
            pystray.MenuItem('更改端口', on_change_port),
        )),
        pystray.MenuItem('日志管理', pystray.Menu(
            pystray.MenuItem('查看日志信息', on_view_log_info),
            pystray.MenuItem('清理日志', on_clean_logs),
        )),
        pystray.MenuItem('开机自启：' + ('已开启' if autostart else '未开启'), on_toggle_autostart),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem('控制台', pystray.Menu(
            pystray.MenuItem('显示/隐藏', toggle_console_window),
            pystray.MenuItem('清理内容', on_clear_console),
            pystray.MenuItem('状态：' + ('可见' if config.CONSOLE_VISIBLE else '隐藏'), None, enabled=False),
        )),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem('版本更新', on_open_upgrade),
        pystray.MenuItem('GitHub仓库', on_open_github),
        pystray.MenuItem('赞助作者', on_donate),
        pystray.MenuItem('二维码生成插件', on_open_qr_plugin),
        pystray.MenuItem('退出', on_quit)
    )


def setup_tray():
    """设置系统托盘"""
    import platform
    try:
        windows_version = platform.release()
        windows_build = None
        if hasattr(sys, 'getwindowsversion'):
            win_info = sys.getwindowsversion()
            windows_build = win_info.build if hasattr(win_info, 'build') else None
        is_win7 = windows_version == "7"
        is_win11 = windows_build and windows_build >= 22000 if windows_build else False
    except Exception:
        is_win7 = False
        is_win11 = False
    try:
        logo_path = None
        candidate_paths = []
        if hasattr(sys, '_MEIPASS'):
            candidate_paths.extend([
                path_manager.get_resource_path(os.path.join('resources', 'logo.ico')),
                path_manager.get_resource_path('logo.ico'),
                os.path.join(os.path.dirname(sys.executable), 'logo.ico'),
            ])
        else:
            candidate_paths.extend([
                path_manager.get_resource_path(os.path.join('resources', 'logo.ico')),
                path_manager.get_resource_path('logo.ico'),
                os.path.join(os.path.dirname(os.path.abspath(__file__)), 'resources', 'logo.ico'),
                os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logo.ico'),
                os.path.join(os.getcwd(), 'resources', 'logo.ico'),
                os.path.join(os.getcwd(), 'logo.ico'),
            ])
        candidate_paths.extend([
            'logo.ico',
            path_manager.get_data_path('logo.ico'),
            path_manager.get_data_path(os.path.join('resources', 'logo.ico')),
        ])
        for path in candidate_paths:
            if os.path.exists(path):
                logo_path = path
                break
        if logo_path:
            try:
                image = Image.open(logo_path)
            except Exception as e:
                print(f"加载图标失败: {e}")
                logo_path = None
        if not logo_path:
            image = Image.new('RGB', (32, 32), color='blue')
            draw = ImageDraw.Draw(image)
            draw.text((12, 12), "P", fill='white')
        icon_title = '内网打印及扫描服务 - by 忆痕'
        icon = pystray.Icon('print_server', image, icon_title)
        icon.menu = build_menu(icon)
        try:
            icon.run()
        except Exception as e:
            error_msg = f"系统托盘功能启动失败\n\n错误信息: {str(e)}\n\n"
            if is_win7:
                error_msg += "Win7系统托盘兼容性问题较常见\n"
            elif is_win11:
                error_msg += "Win11可能需要管理员权限\n"
            from app import app
            error_msg += f"您仍可以通过以下方式使用：\n• http://{get_local_ip()}:{getattr(app, 'current_port', 5000)}"
            show_error_dialog("系统托盘启动失败", error_msg, is_critical=False)
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                sys.exit(0)
    except Exception as e:
        print(f"系统托盘初始化失败: {e}")
        show_error_dialog("系统托盘初始化失败", f"无法初始化系统托盘\n\n错误详情: {str(e)}", is_critical=False)
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            sys.exit(0)


def check_admin_privileges():
    """检查是否以管理员模式运行"""
    try:
        import ctypes
        return ctypes.windll.shell32.IsUserAnAdmin()
    except Exception:
        return False


def check_windows_features():
    """检查Windows特性和服务"""
    issues = []
    suggestions = []
    try:
        result = subprocess.run(['sc', 'query', 'Spooler'],
                              capture_output=True, text=True, timeout=5)
        if 'RUNNING' not in result.stdout:
            issues.append("Windows打印服务未运行")
            suggestions.append("启动打印服务：sc start Spooler")
    except Exception:
        pass
    try:
        result = subprocess.run(['netsh', 'advfirewall', 'show', 'allprofiles', 'state'],
                              capture_output=True, text=True, timeout=5)
        if 'ON' in result.stdout:
            suggestions.append("如果无法访问服务，可能需要在防火墙中允许Python或此程序")
    except Exception:
        pass
    return issues, suggestions
