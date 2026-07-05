#!/usr/bin/env python
# -*- coding: utf-8 -*-
#作者：忆痕
#仓库地址：https://github.com/a937750307/lan-printing

"""服务管理器 - ServiceManager类、健康监控、Flask/WSGI服务运行"""

import os
import sys
import time
import threading


class ServiceManager:
    """服务管理器，用于管理Flask服务和程序重启"""
    def __init__(self):
        self.flask_thread = None
        self.cleaner_thread = None
        self.monitor_thread = None
        self.should_restart = False
        self.restart_port = None
        self.service_running = False
        self.last_health_check = time.time()
        self.health_check_interval = 600
        self.health_fail_count = 0
        self.start_time = None
        self._optimize_for_windows_version()
        self.is_shutting_down = False

    def _optimize_for_windows_version(self):
        """统一服务管理参数"""
        self.health_check_interval = 600
        self.max_restart_attempts = 5
        self.restart_cooldown = 300
        self.restart_count = 0
        self.last_restart_time = 0
        print("服务管理参数已统一设置：检查间隔600秒，最多重启5次，冷却300秒")

    def set_restart(self, port):
        self.should_restart = True
        self.restart_port = port

    def is_restart_requested(self):
        return self.should_restart

    def get_restart_port(self):
        return self.restart_port

    def clear_restart(self):
        self.should_restart = False
        self.restart_port = None

    def mark_service_running(self):
        self.service_running = True
        self.last_health_check = time.time()
        if self.start_time is None:
            self.start_time = time.time()
        self.health_fail_count = 0

    def mark_service_stopped(self):
        self.service_running = False

    def is_service_healthy(self):
        if not self.service_running:
            return False
        if self.flask_thread and not self.flask_thread.is_alive():
            return False
        return True

    def update_health_check(self):
        self.last_health_check = time.time()

    def restart_flask_service(self):
        """重启Flask服务 - 增强稳定性版本"""
        current_time = time.time()
        if self.is_shutting_down:
            print("程序正在关闭，跳过服务重启")
            return False
        if current_time - self.last_restart_time < self.restart_cooldown:
            remaining = self.restart_cooldown - (current_time - self.last_restart_time)
            print(f"重启冷却中，还需等待 {remaining:.1f} 秒")
            return False
        if self.restart_count >= self.max_restart_attempts:
            print(f"已达到最大重启次数 ({self.max_restart_attempts})，停止重启")
            return False
        try:
            self.restart_count += 1
            self.last_restart_time = current_time
            print(f"检测到服务异常，正在重启Flask服务... (第{self.restart_count}次)")
            self.mark_service_stopped()
            if self.flask_thread and self.flask_thread.is_alive():
                self.flask_thread.join(timeout=10)
            time.sleep(2)
            # 延迟导入避免循环依赖
            from app import app
            port = getattr(app, 'current_port', 5000)
            app.current_port = port
            if os.environ.get('USE_WSGI', '').lower() == 'true':
                self.flask_thread = threading.Thread(target=run_wsgi, daemon=True, name="FlaskWSGI")
            else:
                self.flask_thread = threading.Thread(target=run_flask, daemon=True, name="FlaskDev")
            self.flask_thread.start()
            time.sleep(3)
            if self.flask_thread.is_alive():
                self.mark_service_running()
                print(f" Flask服务重启成功 (第{self.restart_count}次)")
                if self.restart_count >= 3:
                    self.restart_count = max(0, self.restart_count - 2)
                return True
            else:
                print(f" Flask服务重启失败")
                return False
        except Exception as e:
            print(f"Flask服务重启异常: {e}")
            return False


# 全局服务管理器实例
service_manager = ServiceManager()


def monitor_service_health():
    """监控服务健康状态，发现异常时自动重启"""
    startup_message_shown = False
    last_check_time = 0
    while True:
        try:
            current_time = time.time()
            if hasattr(service_manager, 'start_time') and service_manager.start_time:
                uptime = current_time - service_manager.start_time
                if uptime > 3600:
                    check_interval = 1800
                elif uptime > 1800:
                    check_interval = 900
                else:
                    check_interval = service_manager.health_check_interval
            else:
                check_interval = service_manager.health_check_interval
            if current_time - last_check_time < check_interval:
                time.sleep(30)
                continue
            last_check_time = current_time
            if not service_manager.is_service_healthy():
                print(" 检测到Flask服务异常")
                service_manager.restart_flask_service()
                startup_message_shown = False
                continue
            if service_manager.start_time and (current_time - service_manager.start_time) < 10:
                if not startup_message_shown:
                    print(" 服务启动中，健康检查暂停10秒...")
                    startup_message_shown = True
                continue
            try:
                import socket
                from app import app
                port = getattr(app, 'current_port', 5000)
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(2)
                result = sock.connect_ex(('127.0.0.1', port))
                sock.close()
                if result == 0:
                    service_manager.update_health_check()
                    service_manager.health_fail_count = 0
                else:
                    service_manager.health_fail_count += 1
                    if service_manager.health_fail_count >= 2:
                        print(" 连续Socket检查失败，重启服务")
                        service_manager.restart_flask_service()
                        service_manager.health_fail_count = 0
            except Exception as e:
                print(f" Socket健康检查异常: {e}")
                service_manager.health_fail_count = getattr(service_manager, 'health_fail_count', 0) + 1
                if service_manager.health_fail_count >= 2:
                    service_manager.restart_flask_service()
                    service_manager.health_fail_count = 0
        except Exception as e:
            print(f"服务监控异常: {e}")
            time.sleep(30)


def run_flask():
    """运行Flask服务"""
    from app import app
    port = getattr(app, 'current_port', 5000)
    max_restart_attempts = 3
    restart_count = 0
    while restart_count < max_restart_attempts:
        try:
            print(f" 正在启动Flask服务 (端口:{port}, 尝试:{restart_count + 1}/{max_restart_attempts})...")
            service_manager.mark_service_running()
            from werkzeug.serving import WSGIRequestHandler
            class OptimizedRequestHandler(WSGIRequestHandler):
                def handle_one_request(self):
                    try:
                        super().handle_one_request()
                    except Exception as e:
                        if 'Connection aborted' not in str(e) and 'Broken pipe' not in str(e):
                            print(f" 请求处理异常: {e}")
                def log_error(self, format, *args):
                    error_msg = format % args if args else format
                    if any(ignore in error_msg for ignore in [
                        'Connection aborted', 'Broken pipe', 'Connection reset',
                        'Bad file descriptor', 'Invalid HTTP method'
                    ]):
                        return
                    super().log_error(format, *args)
            app.run(
                host='0.0.0.0', port=port, use_reloader=False,
                threaded=True, debug=False, request_handler=OptimizedRequestHandler,
                processes=1, passthrough_errors=False
            )
            break
        except OSError as e:
            service_manager.mark_service_stopped()
            if "Address already in use" in str(e):
                print(f" 端口 {port} 已被占用，Flask服务启动失败")
                break
            else:
                print(f" Flask服务启动失败: {e}")
                restart_count += 1
                if restart_count < max_restart_attempts:
                    time.sleep(5)
        except Exception as e:
            service_manager.mark_service_stopped()
            print(f" Flask服务异常停止: {e}")
            restart_count += 1
            if restart_count < max_restart_attempts and service_manager.service_running:
                time.sleep(5 * restart_count)
            else:
                break


def get_waitress_config_for_windows():
    """根据Windows版本返回优化的Waitress配置"""
    import platform
    try:
        windows_version = platform.release()
        windows_build = None
        if hasattr(sys, 'getwindowsversion'):
            win_info = sys.getwindowsversion()
            windows_build = win_info.build if hasattr(win_info, 'build') else None
        is_win7 = windows_version == "7"
        is_win11 = windows_build and windows_build >= 22000 if windows_build else False
        if is_win7:
            return {
                'threads': 4, 'connection_limit': 50, 'cleanup_interval': 120,
                'channel_timeout': 180, 'max_request_body_size': 52428800,
                'send_bytes': 4096, 'asyncore_use_poll': False, 'backlog': 32, 'recv_bytes': 4096
            }
        elif is_win11:
            return {
                'threads': 12, 'connection_limit': 500, 'cleanup_interval': 30,
                'channel_timeout': 600, 'max_request_body_size': 209715200,
                'send_bytes': 16384, 'asyncore_use_poll': True, 'backlog': 128, 'recv_bytes': 16384
            }
        else:
            return {
                'threads': 8, 'connection_limit': 200, 'cleanup_interval': 60,
                'channel_timeout': 300, 'max_request_body_size': 104857600,
                'send_bytes': 8192, 'asyncore_use_poll': True, 'backlog': 64, 'recv_bytes': 8192
            }
    except Exception as e:
        print(f" Waitress配置检测失败: {e}")
        return {
            'threads': 6, 'connection_limit': 100, 'cleanup_interval': 90,
            'channel_timeout': 240, 'max_request_body_size': 104857600,
            'send_bytes': 8192, 'asyncore_use_poll': True, 'backlog': 64, 'recv_bytes': 8192
        }


def run_wsgi():
    """运行WSGI服务 - 生产环境优化版本"""
    from app import app
    port = getattr(app, 'current_port', 5000)
    max_restart_attempts = 3
    restart_count = 0
    try:
        from waitress import serve
        from waitress.server import create_server
        while restart_count < max_restart_attempts:
            try:
                print(f" 正在启动WSGI服务 (端口:{port}, 尝试:{restart_count + 1}/{max_restart_attempts})...")
                service_manager.mark_service_running()
                config = get_waitress_config_for_windows()
                server = create_server(app, host='0.0.0.0', port=port, **config)
                print(f" WSGI服务器配置完成，开始监听...")
                server.run()
                break
            except OSError as e:
                service_manager.mark_service_stopped()
                if "Address already in use" in str(e):
                    print(f" 端口 {port} 已被占用，WSGI服务启动失败")
                    break
                else:
                    restart_count += 1
                    if restart_count < max_restart_attempts:
                        time.sleep(5 * restart_count)
            except Exception as e:
                service_manager.mark_service_stopped()
                print(f" WSGI服务异常停止: {e}")
                restart_count += 1
                if restart_count < max_restart_attempts and service_manager.service_running:
                    time.sleep(5 * restart_count)
                else:
                    break
    except ImportError:
        print(" Waitress未安装，回退到Flask内置服务器")
        run_flask()
