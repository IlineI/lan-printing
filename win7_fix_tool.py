import os
import sys
import platform
import subprocess
import ctypes
import threading

def check_spooler():
    # 检查打印服务(Spooler)是否正在运行
    try:
        result = subprocess.run(['sc', 'query', 'Spooler'], capture_output=True, text=True, timeout=5)
        return 'RUNNING' in result.stdout
    except Exception:
        return False

def check_vc_redist():
    # 检查VC运行库是否安装
    try:
        import winreg
        keys = [
            r"SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64",
            r"SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x86",
            r"SOFTWARE\Microsoft\VisualStudio\12.0\VC\Runtimes\x64",
            r"SOFTWARE\Microsoft\VisualStudio\12.0\VC\Runtimes\x86",
        ]
        for key in keys:
            try:
                hkey = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key)
                value, _ = winreg.QueryValueEx(hkey, "Installed")
                if value == 1:
                    return True
            except Exception:
                continue
        return False
    except Exception:

        # ===== 顶部导入 =====
        import os
        import sys
        import platform
        import subprocess
        import ctypes
        import threading

        # ===== 检查函数 =====
        def is_win7():
            return platform.system() == "Windows" and platform.release() == "7"

        def check_admin():
            try:
                return ctypes.windll.shell32.IsUserAnAdmin()
            except:
                return False

        def check_spooler():
            try:
                result = subprocess.run(['sc', 'query', 'Spooler'], capture_output=True, text=True, timeout=5)
                return 'RUNNING' in result.stdout
            except:
                return False

        def check_vc_redist():
            try:
                import winreg
                keys = [
                    r"SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64",
                    r"SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x86",
                    r"SOFTWARE\Microsoft\VisualStudio\12.0\VC\Runtimes\x64",
                    r"SOFTWARE\Microsoft\VisualStudio\12.0\VC\Runtimes\x86",
                ]
                for key in keys:
                    try:
                        hkey = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key)
                        value, _ = winreg.QueryValueEx(hkey, "Installed")
                        if value == 1:
                            return True
                    except Exception:
                        continue
                return False
            except Exception:
                return False

        def check_dotnet():
            try:
                import winreg
                key_path = r"SOFTWARE\Microsoft\NET Framework Setup\NDP\v4\Full"
                try:
                    hkey = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path)
                    value, _ = winreg.QueryValueEx(hkey, "Release")
                    if value >= 378389:
                        return True
                except Exception:
                    pass
                key_path_35 = r"SOFTWARE\Microsoft\NET Framework Setup\NDP\v3.5"
                try:
                    hkey = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path_35)
                    value, _ = winreg.QueryValueEx(hkey, "Install")
                    if value == 1:
                        return True
                except Exception:
                    pass
                return False
            except Exception:
                return False

        def check_printer_driver():
            try:
                import win32print
                printers = win32print.EnumPrinters(win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS)
                for p in printers:
                    if p[2] and p[2] != 'Microsoft XPS Document Writer':
                        return True
                return False
            except:
                return False

        def check_updates():
            try:
                import winreg
                key_path = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Component Based Servicing\Packages"
                hkey = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path)
                count = winreg.QueryInfoKey(hkey)[0]
                for i in range(count):
                    subkey = winreg.EnumKey(hkey, i)
                    if "KB3033929" in subkey:
                        sub_hkey = winreg.OpenKey(hkey, subkey)
                        try:
                            value, _ = winreg.QueryValueEx(sub_hkey, "CurrentState")
                            if value == 112:
                                return True
                        except Exception:
                            continue
                return False
            except Exception:
                return False

        def check_windows_update():
            try:
                result = subprocess.run(['sc', 'query', 'wuauserv'], capture_output=True, text=True, timeout=5)
                return 'RUNNING' in result.stdout
            except:
                return False

        def check_system_time():
            try:
                import time
                local_time = time.time()
                net_time = None
                try:
                    import requests
                    net_time = requests.get('http://worldtimeapi.org/api/ip', timeout=3).json()['unixtime']
                except Exception:
                    print("未检测到网络时间，仅参考本地时间。")
                    return True
                if net_time:
                    diff = abs(local_time - net_time)
                    return diff < 300
                return True
            except Exception:
                return True

        def check_disk_space():
            try:
                import shutil
                total, used, free = shutil.disk_usage(os.environ.get('SystemDrive', 'C:') + '\\')
                return free > 500*1024*1024
            except:
                return True

        def check_virtual_machine():
            try:
                import platform
                if 'Virtual' in platform.platform() or 'VMware' in platform.platform():
                    return True
                return False
            except:
                return False

        def check_security_software():
            try:
                import psutil
                processes = [p.name().lower() for p in psutil.process_iter()]
                for name in ['360tray.exe', 'kxetray.exe', 'rstray.exe', 'avp.exe', 'zhudongfangyu.exe', 'firefox.exe', 'qqpcmgr.exe']:
                    if name in processes:
                        return True
                return False
            except:
                return False

        def check_group_policy():
            try:
                import winreg
                key_path = r"SOFTWARE\Policies\Microsoft\Windows NT\Printers"
                try:
                    hkey = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path)
                    value, _ = winreg.QueryValueEx(hkey, "DisablePrint")
                    if value == 1:
                        return True
                except Exception:
                    pass
                return False
            except Exception:
                return False

        # ===== 修复项列表 =====
        REPAIR_ITEMS = [
            {
                'name': '打印服务(Spooler)',
                'check': check_spooler,
                'fix': lambda: subprocess.run(['sc', 'start', 'Spooler']),
                'timeout': 10
            },
            {
                'name': 'VC运行库',
                'check': check_vc_redist,
                'fix': lambda: os.startfile('https://aka.ms/vs/17/release/vc_redist.x64.exe'),
                'timeout': 10
            },
            {
                'name': '.NET Framework',
                'check': check_dotnet,
                'fix': lambda: os.startfile('https://www.microsoft.com/zh-cn/download/details.aspx?id=30653'),
                'timeout': 10
            },
            {
                'name': 'KB3033929补丁',
                'check': check_updates,
                'fix': lambda: os.startfile('https://www.catalog.update.microsoft.com/Search.aspx?q=KB3033929'),
                'timeout': 10
            },
            {
                'name': 'Windows Update服务',
                'check': check_windows_update,
                'fix': lambda: subprocess.run(['sc', 'start', 'wuauserv']),
                'timeout': 10
            },
        ]

        # ===== 超时修复辅助 =====
        def fix_with_timeout(fix_func, timeout=10):
            result = {'done': False}
            def target():
                try:
                    fix_func()
                    result['done'] = True
                except Exception as e:
                    print(f'修复时出错: {e}')
            t = threading.Thread(target=target)
            t.start()
            t.join(timeout)
            if t.is_alive():
                print('修复超时，可能未完成。')
                return False
            return result['done']

        # ===== 主流程 =====
        def main():
            print("========================================")
            print("Win7打印环境修复工具  by 忆痕（yckj666@52PJ）")
            print("适用系统：Windows 7")
            print("用途：自动检测并修复打印相关环境问题，帮助用户顺利使用打印服务。")
            print("")
            print("【使用方法】")
            print("1. 请右键以管理员身份运行本工具（否则部分修复操作可能失败）。")
            print("2. 工具会自动检测系统环境并尝试修复常见问题。")
            print("3. 检测结果和修复建议会详细显示在窗口中。")
            print("4. 如有下载链接，请复制到浏览器下载并安装。")
            print("5. 如遇不懂的地方，可联系技术支持或反馈GitHub Issues。")
            print("========================================")
            if not is_win7():
                print("当前系统不是Windows 7，建议使用对应版本修复工具！")
                sys.exit(1)
            print("\n【关键检测项】")
            print("管理员权限：{}".format("是" if check_admin() else "否 (请右键以管理员身份运行)"))
            print("打印服务(Spooler)：{}".format("正常" if check_spooler() else "异常 (请启动打印服务)"))
            print("VC运行库：{}".format("已安装" if check_vc_redist() else "缺失 (请下载安装)"))
            print(".NET Framework：{}".format("已安装" if check_dotnet() else "缺失 (请下载安装)"))
            print("打印机驱动：{}".format("已安装" if check_printer_driver() else "未安装/不兼容 (请安装官方驱动)"))
            print("KB3033929补丁：{}".format("已安装" if check_updates() else "缺失 (建议安装)"))
            print("Windows Update服务：{}".format("已开启" if check_windows_update() else "未开启/被禁用 (建议开启)"))
            print("\n【次要检测项（仅供参考）】")
            print("系统时间：{}".format("正常" if check_system_time() else "异常，建议同步网络时间"))
            print("磁盘空间：{}".format("充足" if check_disk_space() else "不足，建议清理系统盘"))
            print("虚拟机/远程桌面环境：{}".format("检测到" if check_virtual_machine() else "无"))
            print("安全软件拦截：{}".format("可能存在" if check_security_software() else "未检测到"))
            print("\n如遇特殊问题，可参考上述检测结果进一步排查。")
            print("\n【修复建议与教程】")
            print("1. 管理员权限：右键本工具，选择‘以管理员身份运行’。")
            print("2. 打印服务异常：在命令提示符输入 sc start Spooler 并回车。")
            print("3. VC运行库缺失：下载并安装 https://aka.ms/vs/17/release/vc_redist.x86.exe 和 https://aka.ms/vs/17/release/vc_redist.x64.exe。")
            print("4. .NET Framework缺失：下载并安装 https://www.microsoft.com/zh-cn/download/details.aspx?id=30653。")
            print("5. KB3033929补丁缺失：访问 https://www.catalog.update.microsoft.com/Search.aspx?q=KB3033929 下载并安装。")
            print("6. 打印机驱动：建议到打印机官网或 Windows 设备管理器下载安装。")
            print("7. Windows Update服务未开启：在命令提示符输入 sc start wuauserv 并回车。")
            print("8. 其他问题：可参考 https://msdn.itellyou.cn/ 获取系统补丁合集。")
            print("========================================\n")
            print("\n【可选修复项目】")
            for idx, item in enumerate(REPAIR_ITEMS, 1):
                status = '√' if item['check']() else '×'
                print(f"{idx}. {item['name']} [{status}]")
            print("\n请输入要修复的项目序号（如 1,3 或 0 全部修复），直接回车跳过：")
            choice = input("输入序号：").strip()
            if not choice:
                print("未选择任何修复项，直接退出。")
                return
            if choice == '0':
                selected = list(range(1, len(REPAIR_ITEMS)+1))
            else:
                selected = []
                for c in choice.split(','):
                    try:
                        n = int(c)
                        if 1 <= n <= len(REPAIR_ITEMS):
                            selected.append(n)
                    except:
                        pass
            print("\n开始修复...")
            for i in selected:
                item = REPAIR_ITEMS[i-1]
                print(f"修复：{item['name']} ...", end='')
                ok = fix_with_timeout(item['fix'], item['timeout'])
                print("完成" if ok else "失败")
            print("\n修复流程结束，建议重启电脑后再次检测。按任意键退出...")
            input()

        if __name__ == '__main__':
            main()