#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Windows系统通用修复工具
支持 Win7/Win10/Win11 的自动检测和修复
作者：忆痕
"""

import os
import sys
import platform
import subprocess
import ctypes
import time
import json
import winreg
from pathlib import Path

class WindowsFixTool:
    def __init__(self):
        self.system_info = self._get_system_info()
        self.issues = []
        self.fixes_applied = []
        
    def _get_system_info(self):
        """获取系统信息"""
        try:
            return {
                'system': platform.system(),
                'release': platform.release(),
                'version': platform.version(),
                'machine': platform.machine(),
                'processor': platform.processor(),
                'python_version': platform.python_version(),
                'is_admin': self._is_admin(),
                'windows_version': self._detect_windows_version()
            }
        except Exception as e:
            return {'error': str(e)}
    
    def _is_admin(self):
        """检查管理员权限"""
        try:
            return ctypes.windll.shell32.IsUserAnAdmin()
        except:
            return False
    
    def _detect_windows_version(self):
        """检测Windows版本"""
        try:
            version = platform.platform()
            release = platform.release()
            
            if "Windows-11" in version or release == "11":
                return "win11"
            elif "Windows-10" in version or release == "10":
                return "win10"
            elif "Windows-7" in version or release == "7":
                return "win7"
            elif "Windows-8" in version:
                return "win8"
            else:
                return "unknown"
        except:
            return "unknown"
    
    def diagnose(self):
        """运行完整诊断"""
        print(f"🔍 开始诊断 {self.system_info.get('windows_version', 'Unknown').upper()} 系统...")
        
        # 通用检查
        self._check_dependencies()
        self._check_file_permissions()
        self._check_network_permissions()
        self._check_path_compatibility()
        
        # 系统特定检查
        win_version = self.system_info.get('windows_version')
        if win_version == 'win11':
            self._check_win11_specific()
        elif win_version == 'win10':
            self._check_win10_specific()
        elif win_version == 'win7':
            self._check_win7_specific()
        
        return {
            'system_info': self.system_info,
            'issues': self.issues,
            'fixes_available': len(self.issues) > 0
        }
    
    def _check_dependencies(self):
        """检查依赖库"""
        required_libs = [
            ('win32print', 'Windows打印支持'),
            ('win32api', 'Windows API'),
            ('pystray', '系统托盘'),
            ('PIL', '图像处理'),
            ('flask', 'Web服务器')
        ]
        
        missing = []
        for lib, desc in required_libs:
            try:
                __import__(lib)
            except ImportError:
                missing.append((lib, desc))
        
        if missing:
            self.issues.append({
                'type': 'dependency',
                'severity': 'high',
                'title': '依赖库缺失',
                'description': f'缺少 {len(missing)} 个关键依赖库',
                'details': missing,
                'fix': 'reinstall_dependencies'
            })
    
    def _check_file_permissions(self):
        """检查文件权限"""
        try:
            test_file = os.path.join(os.path.dirname(__file__), 'permission_test.tmp')
            with open(test_file, 'w') as f:
                f.write('test')
            os.remove(test_file)
        except Exception as e:
            self.issues.append({
                'type': 'permission',
                'severity': 'high',
                'title': '文件权限不足',
                'description': '程序目录没有写入权限',
                'details': str(e),
                'fix': 'elevate_permissions'
            })
    
    def _check_network_permissions(self):
        """检查网络权限"""
        try:
            import socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.bind(('127.0.0.1', 0))
            sock.close()
        except Exception as e:
            self.issues.append({
                'type': 'network',
                'severity': 'medium',
                'title': '网络权限受限',
                'description': '无法绑定网络端口',
                'details': str(e),
                'fix': 'configure_firewall'
            })
    
    def _check_path_compatibility(self):
        """检查路径兼容性"""
        current_path = os.path.abspath(__file__)
        issues = []
        
        # 检查中文字符
        try:
            current_path.encode('ascii')
        except UnicodeEncodeError:
            issues.append('包含中文字符')
        
        # 检查路径长度
        if len(current_path) > 200:
            issues.append('路径过长')
        
        # 检查特殊字符
        special_chars = ['&', '%', '#', '@', '!']
        for char in special_chars:
            if char in current_path:
                issues.append(f'包含特殊字符: {char}')
                break
        
        if issues:
            self.issues.append({
                'type': 'path',
                'severity': 'medium',
                'title': '路径兼容性问题',
                'description': ', '.join(issues),
                'details': current_path,
                'fix': 'optimize_path'
            })
    
    def _check_win11_specific(self):
        """Win11特有检查"""
        # Windows Defender检查
        try:
            current_dir = os.path.dirname(os.path.abspath(__file__))
            cmd = ['powershell', '-Command', 'Get-MpPreference | Select-Object -ExpandProperty ExclusionPath']
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            
            if result.returncode == 0:
                exclusions = result.stdout.strip().split('\n')
                is_excluded = any(current_dir.lower().startswith(ex.lower()) for ex in exclusions if ex.strip())
                
                if not is_excluded:
                    self.issues.append({
                        'type': 'defender',
                        'severity': 'high',
                        'title': 'Windows Defender拦截',
                        'description': '程序未在Defender排除列表中',
                        'details': current_dir,
                        'fix': 'add_defender_exclusion'
                    })
        except:
            pass
        
        # SmartScreen检查
        self.issues.append({
            'type': 'smartscreen',
            'severity': 'low',
            'title': 'SmartScreen可能拦截',
            'description': 'Win11的SmartScreen较为严格',
            'details': '未签名的exe文件可能被拦截',
            'fix': 'configure_smartscreen'
        })
    
    def _check_win10_specific(self):
        """Win10特有检查"""
        # 检查Windows Defender（比Win11宽松）
        try:
            # 简单的Defender状态检查
            cmd = ['powershell', '-Command', 'Get-MpComputerStatus']
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            
            if 'RealTimeProtectionEnabled : True' in result.stdout:
                self.issues.append({
                    'type': 'defender',
                    'severity': 'medium',
                    'title': 'Windows Defender实时保护',
                    'description': '可能会拦截程序运行',
                    'details': '建议添加排除项',
                    'fix': 'add_defender_exclusion'
                })
        except:
            pass
    
    def _check_win7_specific(self):
        """Win7特有检查"""
        # 检查.NET Framework
        try:
            import winreg
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, 
                               r"SOFTWARE\Microsoft\NET Framework Setup\NDP\v4\Full")
            version, _ = winreg.QueryValueEx(key, "Release")
            winreg.CloseKey(key)
            
            if version < 461808:  # .NET 4.7.2
                self.issues.append({
                    'type': 'framework',
                    'severity': 'high',
                    'title': '.NET Framework版本过低',
                    'description': '需要.NET Framework 4.7.2或更高版本',
                    'details': f'当前版本: {version}',
                    'fix': 'update_dotnet'
                })
        except:
            self.issues.append({
                'type': 'framework',
                'severity': 'medium',
                'title': '.NET Framework状态未知',
                'description': '无法检测.NET Framework版本',
                'details': '可能需要安装或更新',
                'fix': 'install_dotnet'
            })
        
        # 检查Windows Update
        self.issues.append({
            'type': 'update',
            'severity': 'low',
            'title': 'Windows 7更新建议',
            'description': '建议安装最新的Windows更新',
            'details': '某些功能可能需要系统更新',
            'fix': 'windows_update'
        })
    
    def apply_fixes(self, fix_types=None):
        """应用修复"""
        if not fix_types:
            fix_types = [issue['fix'] for issue in self.issues]
        
        results = {}
        
        for fix_type in fix_types:
            try:
                if hasattr(self, f'_fix_{fix_type}'):
                    result = getattr(self, f'_fix_{fix_type}')()
                    results[fix_type] = result
                    if result.get('success'):
                        self.fixes_applied.append(fix_type)
                else:
                    results[fix_type] = {'success': False, 'message': '修复方法未实现'}
            except Exception as e:
                results[fix_type] = {'success': False, 'message': str(e)}
        
        return results
    
    def _fix_elevate_permissions(self):
        """提升权限"""
        if not self._is_admin():
            try:
                # 尝试重新以管理员权限启动
                script = sys.argv[0]
                params = ' '.join(sys.argv[1:])
                ctypes.windll.shell32.ShellExecuteW(
                    None, "runas", sys.executable, f'"{script}" {params}', None, 1
                )
                return {'success': True, 'message': '正在以管理员权限重新启动'}
            except Exception as e:
                return {'success': False, 'message': f'权限提升失败: {e}'}
        return {'success': True, 'message': '已有管理员权限'}
    
    def _fix_add_defender_exclusion(self):
        """添加Defender排除项"""
        if not self._is_admin():
            return {'success': False, 'message': '需要管理员权限'}
        
        try:
            current_dir = os.path.dirname(os.path.abspath(__file__))
            cmd = ['powershell', '-Command', f'Add-MpPreference -ExclusionPath "{current_dir}"']
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            
            if result.returncode == 0:
                return {'success': True, 'message': '成功添加Defender排除项'}
            else:
                return {'success': False, 'message': f'添加失败: {result.stderr}'}
        except Exception as e:
            return {'success': False, 'message': f'操作失败: {e}'}
    
    def _fix_configure_firewall(self):
        """配置防火墙"""
        if not self._is_admin():
            return {'success': False, 'message': '需要管理员权限'}
        
        try:
            # 为Python程序添加防火墙例外
            cmd = [
                'netsh', 'advfirewall', 'firewall', 'add', 'rule',
                'name=内网打印服务', 'dir=in', 'action=allow',
                f'program={sys.executable}'
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode == 0:
                return {'success': True, 'message': '防火墙规则添加成功'}
            else:
                return {'success': False, 'message': f'防火墙配置失败: {result.stderr}'}
        except Exception as e:
            return {'success': False, 'message': f'操作失败: {e}'}
    
    def _fix_optimize_path(self):
        """路径优化建议"""
        current_path = os.path.abspath(__file__)
        suggested_path = "C:\\Tools\\PrintService\\"
        
        return {
            'success': False,
            'message': f'建议将程序移动到: {suggested_path}',
            'action': 'manual',
            'details': {
                'current': current_path,
                'suggested': suggested_path
            }
        }
    
    def _fix_configure_smartscreen(self):
        """SmartScreen配置指导"""
        return {
            'success': False,
            'message': '请手动配置SmartScreen设置',
            'action': 'manual',
            'details': {
                'steps': [
                    '打开Windows设置',
                    '隐私和安全性 → Windows安全中心',
                    '应用和浏览器控制',
                    '调整基于信誉的保护设置'
                ]
            }
        }
    
    def generate_report(self):
        """生成修复报告"""
        report = {
            'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
            'system_info': self.system_info,
            'issues_found': len(self.issues),
            'fixes_applied': len(self.fixes_applied),
            'issues': self.issues,
            'applied_fixes': self.fixes_applied
        }
        
        report_file = f"repair_report_{self.system_info.get('windows_version', 'unknown')}.json"
        
        try:
            with open(report_file, 'w', encoding='utf-8') as f:
                json.dump(report, f, ensure_ascii=False, indent=2)
            return {'success': True, 'file': report_file}
        except Exception as e:
            return {'success': False, 'error': str(e)}

def run_interactive_fix():
    """交互式修复"""
    tool = WindowsFixTool()
    
    print("=" * 60)
    print(f"    Windows修复工具 - {tool.system_info.get('windows_version', 'Unknown').upper()}")
    print("           作者：忆痕")
    print("=" * 60)
    
    # 诊断
    diagnosis = tool.diagnose()
    
    if not diagnosis['fixes_available']:
        print("✅ 系统检查通过，未发现问题！")
        return True
    
    print(f"\n⚠️ 发现 {len(tool.issues)} 个问题:")
    for i, issue in enumerate(tool.issues, 1):
        severity_icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}
        print(f"{i}. {severity_icon.get(issue['severity'], '⚪')} {issue['title']}")
        print(f"   {issue['description']}")
    
    # 询问是否修复
    choice = input(f"\n是否尝试自动修复这些问题？(y/n): ").lower()
    if choice in ['y', 'yes']:
        print("\n🔧 开始修复...")
        results = tool.apply_fixes()
        
        for fix_type, result in results.items():
            if result.get('success'):
                print(f"✅ {fix_type}: {result['message']}")
            else:
                print(f"❌ {fix_type}: {result['message']}")
    
    # 生成报告
    report_result = tool.generate_report()
    if report_result.get('success'):
        print(f"\n📊 修复报告已保存: {report_result['file']}")
    
    return True

if __name__ == '__main__':
    try:
        run_interactive_fix()
    except KeyboardInterrupt:
        print("\n\n用户中断操作")
    except Exception as e:
        print(f"\n修复工具出错: {e}")
        import traceback
        traceback.print_exc()
    
    input("\n按任意键退出...")