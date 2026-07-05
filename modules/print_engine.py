#!/usr/bin/env python
# -*- coding: utf-8 -*-
#作者：忆痕
#仓库地址：https://github.com/a937750307/lan-printing

"""打印核心引擎 - 各类型文件打印方法"""

import os
import sys
import io
import time
import subprocess
import tempfile

from modules.config import DC_DUPLEX, DC_COLORDEVICE, DC_PAPERS, DC_PAPERNAMES, DC_ENUMRESOLUTIONS
from modules.config import DC_ORIENTATION, DC_COPIES, DC_TRUETYPE, DC_DRIVER
from modules.config import PAPER_NAMES, VIRTUAL_PRINTERS, DEBUG_MODE
from modules.path_manager import get_poppler_path
from modules.printer_manager import (ensure_printer_connection, get_printer_capabilities,
                             is_physical_printer)
from modules.network import detect_remote_desktop

try:
    import win32print
    import win32con
    import win32api
except ImportError:
    pass

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    pass


def read_text_with_encoding_detection(filepath):
    """智能检测文件编码并读取内容"""
    try:
        encodings_to_try = [
            'utf-8-sig', 'utf-8', 'gbk', 'gb2312', 'cp1252',
            'latin1', 'utf-16', 'utf-16le', 'utf-16be'
        ]
        with open(filepath, 'rb') as f:
            raw_data = f.read()
        try:
            import chardet
            detected = chardet.detect(raw_data)
            if detected and detected['encoding'] and detected['confidence'] > 0.7:
                det_enc = detected['encoding']
                if det_enc in encodings_to_try:
                    encodings_to_try.remove(det_enc)
                encodings_to_try.insert(0, det_enc)
                print(f"检测到编码: {det_enc} (置信度: {detected['confidence']:.2f})")
        except ImportError:
            pass
        for encoding in encodings_to_try:
            try:
                content = raw_data.decode(encoding)
                replacement_ratio = content.count('\ufffd') / len(content) if len(content) > 0 else 0
                if replacement_ratio < 0.1:
                    return content
            except (UnicodeDecodeError, UnicodeError):
                continue
        return raw_data.decode('utf-8', errors='replace')
    except Exception as e:
        print(f"编码检测过程异常: {e}")
        return None


def validate_duplex_setting(printer_name, duplex_value):
    """验证双面打印设置是否被打印机支持"""
    try:
        caps = get_printer_capabilities(printer_name)
        if duplex_value > 1 and not caps.get('duplex_support', False):
            print(f"打印机 '{printer_name}' 不支持双面打印，将改为单面打印")
            return 1
        duplex_modes = caps.get('duplex_modes', [])
        if duplex_value == 2 and 'long_edge' not in duplex_modes:
            if 'short_edge' in duplex_modes:
                return 3
            else:
                return 1
        if duplex_value == 3 and 'short_edge' not in duplex_modes:
            if 'long_edge' in duplex_modes:
                return 2
            else:
                return 1
        return duplex_value
    except Exception as e:
        print(f"验证双面设置时出错: {e}，使用原设置")
        return duplex_value


def save_printer_duplex_setting(printer_name):
    """保存打印机当前的双面打印设置"""
    try:
        printer_handle = win32print.OpenPrinter(printer_name)
        try:
            devmode = win32print.GetPrinter(printer_handle, 2)['pDevMode']
            if devmode:
                current_duplex = devmode.Duplex
                print(f"保存打印机当前双面设置: {current_duplex}")
                return current_duplex
        finally:
            win32print.ClosePrinter(printer_handle)
    except Exception as e:
        print(f"保存打印机双面设置失败: {e}")
    return None


def restore_printer_duplex_setting(printer_name, original_duplex):
    """恢复打印机的原始双面打印设置"""
    if original_duplex is None:
        return False
    try:
        printer_handle = win32print.OpenPrinter(printer_name)
        try:
            devmode = win32print.GetPrinter(printer_handle, 2)['pDevMode']
            if devmode:
                devmode.Duplex = original_duplex
                devmode.Fields |= win32con.DM_DUPLEX
                win32print.SetPrinter(printer_name, 2, {'pDevMode': devmode}, 0)
                print(f"已恢复打印机双面设置为: {original_duplex}")
                return True
        finally:
            win32print.ClosePrinter(printer_handle)
    except Exception as e:
        print(f"恢复打印机双面设置失败: {e}")
    return False


def apply_printer_duplex_setting(printer_name, duplex):
    """临时应用打印机双面设置到打印机硬件配置"""
    if duplex == 1:
        return None
    try:
        original_duplex = save_printer_duplex_setting(printer_name)
        printer_handle = win32print.OpenPrinter(printer_name)
        try:
            devmode = win32print.GetPrinter(printer_handle, 2)['pDevMode']
            if devmode:
                if duplex == 2:
                    devmode.Duplex = win32con.DMDUP_VERTICAL
                    print("临时启用打印机: 双面打印 - 长边翻转")
                elif duplex == 3:
                    devmode.Duplex = win32con.DMDUP_HORIZONTAL
                    print("临时启用打印机: 双面打印 - 短边翻转")
                devmode.Fields |= win32con.DM_DUPLEX
                win32print.SetPrinter(printer_name, 2, {'pDevMode': devmode}, 0)
                print(f"已临时修改打印机双面设置，原始设置已保存")
                return original_duplex
        finally:
            win32print.ClosePrinter(printer_handle)
    except Exception as e:
        print(f"应用打印机双面设置失败: {e}")
    return None


def apply_printer_settings(printer_name, copies, duplex, papersize, quality):
    """应用打印机设置，返回设备模式"""
    try:
        if not printer_name or printer_name.strip() == "":
            return None
        if printer_name == "未检测到可用打印机":
            return None
        original_duplex = duplex
        duplex = validate_duplex_setting(printer_name, duplex)
        if duplex != original_duplex:
            print(f"双面设置已从 {original_duplex} 调整为 {duplex}")
        printer_handle = win32print.OpenPrinter(printer_name)
        try:
            devmode = win32print.GetPrinter(printer_handle, 2)['pDevMode']
            if devmode is None:
                return None
            if copies > 1:
                devmode.Copies = copies
            try:
                if duplex == 1:
                    devmode.Duplex = win32con.DMDUP_SIMPLEX
                elif duplex == 2:
                    devmode.Duplex = win32con.DMDUP_VERTICAL
                elif duplex == 3:
                    devmode.Duplex = win32con.DMDUP_HORIZONTAL
                else:
                    devmode.Duplex = win32con.DMDUP_SIMPLEX
                devmode.Fields |= win32con.DM_DUPLEX
            except Exception as e:
                print(f"设置双面打印失败: {e}")
                try:
                    devmode.Duplex = win32con.DMDUP_SIMPLEX
                    devmode.Fields |= win32con.DM_DUPLEX
                except:
                    pass
            try:
                if isinstance(papersize, int) or (isinstance(papersize, str) and papersize.isdigit()):
                    devmode.PaperSize = int(papersize)
                else:
                    paper_size_map = {
                        'A4': win32con.DMPAPER_A4, 'A3': win32con.DMPAPER_A3,
                        'Letter': win32con.DMPAPER_LETTER, 'Legal': win32con.DMPAPER_LEGAL
                    }
                    if papersize in paper_size_map:
                        devmode.PaperSize = paper_size_map[papersize]
            except Exception as e:
                print(f"设置纸张大小失败: {e}")
            try:
                if isinstance(quality, str) and ('x' in quality or 'X' in quality):
                    parts = quality.lower().replace(' ', '').split('x')
                    if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
                        devmode.PrintQuality = int(parts[0])
                        devmode.YResolution = int(parts[1])
                elif isinstance(quality, int) or (isinstance(quality, str) and quality.isdigit()):
                    devmode.PrintQuality = int(quality)
                else:
                    if quality == 'high':
                        devmode.PrintQuality = win32con.DMRES_HIGH
                    else:
                        devmode.PrintQuality = win32con.DMRES_MEDIUM
            except Exception as e:
                print(f"设置打印质量失败: {e}")
            return devmode
        finally:
            win32print.ClosePrinter(printer_handle)
    except Exception as e:
        print(f"设置打印参数失败: {e}")
        return None


def convert_file_to_bmp_bytes(filepath, max_width=2480, max_height=3508):
    """将文件转换为 BMP 字节流"""
    try:
        ext = os.path.splitext(filepath)[1].lower()
        if ext in ['.jpg', '.jpeg', '.png', '.bmp', '.gif', '.tiff']:
            img = Image.open(filepath).convert('RGB')
        elif ext == '.txt':
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                text = f.read()
            font = ImageFont.load_default()
            lines = text.splitlines() or [' ']
            width = min(max_width, max([font.getsize(l)[0] for l in lines]) + 20)
            height = min(max_height, (font.getsize(lines[0])[1] + 2) * len(lines) + 20)
            img = Image.new('RGB', (width, height), 'white')
            draw = ImageDraw.Draw(img)
            y = 10
            for line in lines:
                draw.text((10, y), line, fill='black', font=font)
                y += font.getsize(line)[1] + 2
        elif ext == '.pdf':
            try:
                from pdf2image import convert_from_path
                from modules.path_manager import path_manager
                poppler = get_poppler_path(path_manager)
                pages = convert_from_path(filepath, first_page=1, last_page=1, dpi=300, poppler_path=poppler)
                img = pages[0].convert('RGB')
            except Exception:
                return None
        else:
            try:
                img = Image.open(filepath).convert('RGB')
            except Exception:
                return None
        img.thumbnail((max_width, max_height), Image.LANCZOS)
        bio = io.BytesIO()
        img.save(bio, format='BMP')
        return bio.getvalue()
    except Exception:
        return None


def convert_pdf_to_bmp_pages(filepath, dpi=300, max_width=3508, max_height=4961):
    """将 PDF 转换为高质量位图列表"""
    try:
        from pdf2image import convert_from_path
        from modules.path_manager import path_manager
        poppler = get_poppler_path(path_manager)
        pages = convert_from_path(filepath, dpi=dpi, poppler_path=poppler)
        bmp_list = []
        for img in pages:
            img = img.convert('RGB')
            img.thumbnail((max_width, max_height), Image.LANCZOS)
            bio = io.BytesIO()
            img.save(bio, format='BMP')
            bmp_list.append(bio.getvalue())
        return bmp_list
    except Exception as e:
        print(f"PDF->BMP 多页转换失败: {e}")
        return None


def send_bytes_to_printer_raw(printer_name, data_bytes):
    """将原始字节流通过 WritePrinter 写入打印机"""
    try:
        ph = win32print.OpenPrinter(printer_name)
        try:
            docinfo = ("PythonRaw", None, "RAW")
            win32print.StartDocPrinter(ph, 1, docinfo)
            win32print.StartPagePrinter(ph)
            win32print.WritePrinter(ph, data_bytes)
            win32print.EndPagePrinter(ph)
            win32print.EndDocPrinter(ph)
            return True
        finally:
            win32print.ClosePrinter(ph)
    except Exception as e:
        print(f"直接写流到打印机失败: {e}")
        return False


def send_pdf_pages_to_printer(printer_name, bmp_pages, copies=1):
    """按页将 BMP 流发送至打印机"""
    try:
        for c in range(copies):
            for page_bytes in bmp_pages:
                if not send_bytes_to_printer_raw(printer_name, page_bytes):
                    return False
                time.sleep(0.5)
        return True
    except Exception as e:
        print(f"发送 PDF 位图页到打印机失败: {e}")
        return False


def print_file_silent_fallback(filepath, printer_name, copies=1):
    """备用的静默打印方案 - 4级备用"""
    try:
        for i in range(copies):
            win32api.ShellExecute(0, 'print', filepath, f'/d:"{printer_name}"', '.', win32con.SW_HIDE)
        return True, f"静默打印任务已发送到 {printer_name} ({copies}份)"
    except Exception as e1:
        try:
            bat_content = f'''@echo off\nfor /L %%i in (1,1,{copies}) do (\n    start /min "" "{filepath}"\n)\n'''
            with tempfile.NamedTemporaryFile(mode='w', suffix='.bat', delete=False) as bat_file:
                bat_file.write(bat_content)
                bat_file_path = bat_file.name
            subprocess.run([bat_file_path], creationflags=subprocess.CREATE_NO_WINDOW, shell=True)
            try:
                os.unlink(bat_file_path)
            except:
                pass
            return True, f"静默打印任务已发送 ({copies}份) - 备用方案"
        except Exception as e2:
            try:
                for i in range(copies):
                    subprocess.run(['rundll32.exe', 'mshtml.dll,PrintHTML', filepath],
                                 creationflags=subprocess.CREATE_NO_WINDOW)
                return True, f"基础静默打印已执行 ({copies}份)"
            except Exception as e3:
                try:
                    bmp_bytes = convert_file_to_bmp_bytes(filepath)
                    if bmp_bytes:
                        ok = True
                        for i in range(copies):
                            if not send_bytes_to_printer_raw(printer_name, bmp_bytes):
                                ok = False
                                break
                        if ok:
                            return True, f"已通过位图流发送到 {printer_name} ({copies}份)"
                except Exception as e4:
                    print(f"位图流打印方案失败: {e4}")
                return False, f"所有静默打印方案都失败: {str(e3)}"


def print_with_shell_execute(filepath, printer_name, copies):
    """使用ShellExecute进行应用程序调用打印"""
    try:
        success_count = 0
        for i in range(copies):
            try:
                result = win32api.ShellExecute(0, 'print', filepath, None, None, 0)
                if result > 32:
                    success_count += 1
                    time.sleep(1)
                else:
                    print(f"ShellExecute失败，错误代码: {result}")
            except Exception as e:
                print(f"打印第{i+1}份时出错: {e}")
        if success_count > 0:
            return True, f"通过关联应用程序打印已发送 ({success_count}/{copies}份)"
        return False, "所有打印尝试都失败了"
    except Exception as e:
        return False, f"ShellExecute打印失败: {str(e)}"


def print_pdf_silent(filepath, printer_name, copies=1):
    """专门用于PDF文件的静默打印"""
    try:
        browser_paths = [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        ]
        for browser_path in browser_paths:
            if os.path.exists(browser_path):
                try:
                    for i in range(copies):
                        cmd = [browser_path, '--headless', '--disable-gpu', '--print-to-printer',
                               f'--printer-name={printer_name}', filepath]
                        subprocess.run(cmd, capture_output=True,
                                      creationflags=subprocess.CREATE_NO_WINDOW, timeout=30)
                        time.sleep(2)
                    return True, f"浏览器PDF静默打印已发送到 {printer_name} ({copies}份)"
                except subprocess.TimeoutExpired:
                    print(f"浏览器打印超时，尝试其他方案")
                except Exception as e:
                    print(f"浏览器打印失败: {e}")
        adobe_paths = [
            r"C:\Program Files\Adobe\Acrobat DC\Acrobat\Acrobat.exe",
            r"C:\Program Files (x86)\Adobe\Acrobat Reader DC\Reader\AcroRd32.exe",
            r"C:\Program Files\Adobe\Acrobat Reader DC\Reader\AcroRd32.exe",
            r"C:\Program Files (x86)\Adobe\Reader 11.0\Reader\AcroRd32.exe",
        ]
        adobe_found = False
        for adobe_path in adobe_paths:
            if os.path.exists(adobe_path):
                adobe_found = True
                try:
                    for i in range(copies):
                        cmd = [adobe_path, '/t', filepath, printer_name]
                        subprocess.run(cmd, capture_output=True,
                                      creationflags=subprocess.CREATE_NO_WINDOW, timeout=30)
                        time.sleep(2)
                    return True, f"Adobe PDF静默打印已发送到 {printer_name} ({copies}份)"
                except subprocess.TimeoutExpired:
                    return False, "Adobe Reader打印超时"
                except Exception as e:
                    print(f"Adobe Reader打印失败: {e}")
                    break
        if not adobe_found:
            try:
                for i in range(copies):
                    result = win32api.ShellExecute(0, 'printto', filepath, f'"{printer_name}"', '', win32con.SW_HIDE)
                    if result <= 32:
                        raise Exception(f"ShellExecute失败，错误代码: {result}")
                    time.sleep(3)
                return True, f"默认PDF阅读器打印已发送到 {printer_name} ({copies}份)"
            except Exception as e:
                print(f"默认PDF阅读器打印失败: {e}")
        try:
            bmp_pages = convert_pdf_to_bmp_pages(filepath, dpi=300)
            if bmp_pages:
                sent = send_pdf_pages_to_printer(printer_name, bmp_pages, copies)
                if sent:
                    return True, f"已通过多页位图回退方案发送到 {printer_name} ({copies}份)"
        except Exception as e:
            print(f"多页位图回退方案出错: {e}")
        return print_file_silent_fallback(filepath, printer_name, copies)
    except Exception as e:
        print(f"PDF打印完全失败: {e}")
        return print_file_silent_fallback(filepath, printer_name, copies)


def print_pdf_with_settings(filepath, printer_name, copies, duplex, papersize, quality):
    """使用设置参数打印PDF文件"""
    try:
        adobe_paths = [
            r"C:\\Program Files\\Adobe\\Acrobat DC\\Acrobat\\Acrobat.exe",
            r"C:\\Program Files (x86)\\Adobe\\Acrobat Reader DC\\Reader\\AcroRd32.exe",
            r"C:\\Program Files\\Adobe\\Acrobat Reader DC\\Reader\\AcroRd32.exe"
        ]
        for adobe_path in adobe_paths:
            if os.path.exists(adobe_path):
                try:
                    cmd = f'"{adobe_path}" /p /h "{filepath}"'
                    _ = apply_printer_settings(printer_name, copies, duplex, papersize, quality)
                    result = os.system(cmd)
                    if result == 0:
                        return True
                except Exception as e:
                    print(f"Adobe Reader打印失败: {e}")
                    continue
        return print_pdf_silent(filepath, printer_name, copies)
    except Exception as e:
        print(f"PDF打印失败: {e}")
        return False


def create_notepad_print_batch(filepath, printer_name):
    """创建临时批处理文件实现记事本静默打印"""
    try:
        temp_dir = tempfile.gettempdir()
        bat_file = os.path.join(temp_dir, f"print_text_{int(time.time())}.bat")
        bat_content = f'''@echo off\necho 正在打印文件到 {printer_name}...\ntype "{filepath}" > "\\\\localhost\\{printer_name}"\nif errorlevel 1 (\n    echo 打印失败\n    exit /b 1\n) else (\n    echo 打印成功\n    exit /b 0\n)\n'''
        with open(bat_file, 'w', encoding='gbk') as f:
            f.write(bat_content)
        return bat_file
    except Exception as e:
        print(f"创建批处理文件失败: {e}")
        return None


def try_notepad_print(filepath, printer_name, copies=1):
    """使用Windows自带记事本进行打印"""
    try:
        notepad_path = r"C:\Windows\System32\notepad.exe"
        if not os.path.exists(notepad_path):
            return False, "Windows记事本未找到"
        success_count = 0
        for i in range(copies):
            try:
                temp_bat = create_notepad_print_batch(filepath, printer_name)
                if temp_bat:
                    bat_result = subprocess.run([temp_bat], creationflags=subprocess.CREATE_NO_WINDOW, timeout=30)
                    if bat_result.returncode == 0:
                        success_count += 1
                    try:
                        os.remove(temp_bat)
                    except:
                        pass
                else:
                    r = win32api.ShellExecute(0, 'open', notepad_path, f'/pt "{filepath}" "{printer_name}"', None, 0)
                    if r > 32:
                        success_count += 1
                time.sleep(1)
            except Exception as e:
                print(f"记事本打印第{i+1}份时出错: {e}")
        if success_count > 0:
            return True, f"Windows记事本打印成功 ({success_count}/{copies}份)"
        return False, "Windows记事本打印失败"
    except Exception as e:
        return False, f"记事本打印异常: {e}"


def try_wordpad_print(filepath, printer_name, copies=1):
    """使用WordPad进行打印"""
    try:
        wordpad_path = r"C:\Program Files\Windows NT\Accessories\wordpad.exe"
        if not os.path.exists(wordpad_path):
            wordpad_path = r"C:\Program Files (x86)\Windows NT\Accessories\wordpad.exe"
        if not os.path.exists(wordpad_path):
            return False, "WordPad未找到"
        success_count = 0
        for i in range(copies):
            try:
                cmd = [wordpad_path, '/pt', filepath, printer_name]
                result = subprocess.run(cmd, creationflags=subprocess.CREATE_NO_WINDOW, timeout=30)
                if result.returncode == 0:
                    success_count += 1
                    time.sleep(2)
            except Exception as e:
                print(f"WordPad打印第{i+1}份时出错: {e}")
        if success_count > 0:
            return True, f"WordPad打印成功 ({success_count}/{copies}份)"
        return False, "WordPad打印失败"
    except Exception as e:
        return False, f"WordPad打印异常: {e}"


def print_text_direct_to_printer(filepath, printer_name, copies=1):
    """使用WIN32 API直接将文本文件发送到指定打印机"""
    try:
        print(f" 使用API直接打印: {filepath}")
        content = read_text_with_encoding_detection(filepath)
        if not content:
            return False, "无法读取文本文件内容"
        printer_handle = win32print.OpenPrinter(printer_name)
        try:
            success_count = 0
            for i in range(copies):
                job_id = win32print.StartDocPrinter(printer_handle, 1, ("Text Document", None, "RAW"))
                try:
                    win32print.StartPagePrinter(printer_handle)
                    print_data = None
                    for encoding in ['utf-8', 'gbk', 'cp1252', 'latin1']:
                        try:
                            print_data = content.encode(encoding)
                            break
                        except UnicodeEncodeError:
                            continue
                    if print_data is None:
                        print_data = content.encode('utf-8', errors='replace')
                    win32print.WritePrinter(printer_handle, print_data)
                    win32print.EndPagePrinter(printer_handle)
                    win32print.EndDocPrinter(printer_handle)
                    success_count += 1
                except Exception as e:
                    print(f"打印作业 {i+1} 失败: {e}")
                    win32print.AbortPrinter(printer_handle)
            return True, f"直接打印到 {printer_name} 成功 ({success_count}/{copies}份)"
        finally:
            win32print.ClosePrinter(printer_handle)
    except Exception as e:
        return False, f"直接打印失败: {str(e)}"


def print_text_file_simple(filepath, printer_name, copies=1):
    """改进的TXT文件打印"""
    try:
        is_remote_desktop = detect_remote_desktop()
        try:
            api_success = print_text_direct_to_printer(filepath, printer_name, copies)
            if api_success[0]:
                return api_success
        except Exception as e:
            print(f"直接API打印失败: {e}")
        sent = 0
        for i in range(copies):
            r = win32api.ShellExecute(0, 'printto', filepath, f'"{printer_name}"', None, 0)
            if r > 32:
                sent += 1
                time.sleep(1)
            else:
                r2 = win32api.ShellExecute(0, 'print', filepath, None, None, 0)
                if r2 > 32:
                    sent += 1
        if not is_remote_desktop:
            wordpad_success = try_wordpad_print(filepath, printer_name, copies)
            if wordpad_success[0]:
                return wordpad_success
        if not is_remote_desktop:
            notepad_success = try_notepad_print(filepath, printer_name, copies)
            if notepad_success[0]:
                return notepad_success
        return False, f"所有TXT打印方案都失败，无法发送到指定打印机 {printer_name}"
    except Exception as e:
        return False, f"TXT文件打印失败: {e}"


def print_image_silent(filepath, printer_name, copies=1):
    """专门用于图片文件的静默打印"""
    try:
        for i in range(copies):
            try:
                result = subprocess.run(['mspaint.exe', '/p', filepath],
                                       capture_output=True, timeout=30)
                if result.returncode != 0:
                    print(f"图片打印第{i+1}份失败，返回码: {result.returncode}")
                time.sleep(2)
            except subprocess.TimeoutExpired:
                return False, f"图片打印超时"
            except Exception as e:
                return False, f"图片打印异常: {e}"
        return True, f"图片已发送到打印机 ({copies}份)"
    except Exception as e:
        return False, f"图片打印失败: {e}"


def print_office_silent(filepath, printer_name, copies=1):
    """简化的Office文档打印 - COM + PrintTo备用"""
    import threading
    try:
        file_ext = os.path.splitext(filepath)[1].lower()
        def try_com_print():
            try:
                import win32com.client
                if file_ext in ['.doc', '.docx']:
                    app = win32com.client.Dispatch('Word.Application')
                    app.Visible = False
                    doc = app.Documents.Open(filepath, FileName=filepath)
                    for i in range(copies):
                        doc.PrintOut(PrintToFile=False, OutputFileName='', Printer=printer_name)
                        time.sleep(2)
                    doc.Close(SaveChanges=False)
                    app.Quit()
                    return True, f"Word文档已打印 ({copies}份)"
                elif file_ext in ['.xls', '.xlsx']:
                    app = win32com.client.Dispatch('Excel.Application')
                    app.Visible = False
                    wb = app.Workbooks.Open(filepath)
                    for i in range(copies):
                        wb.PrintOut(PrintToFile=False, PrToFileName='', Printer=printer_name)
                        time.sleep(2)
                    wb.Close(SaveChanges=False)
                    app.Quit()
                    return True, f"Excel表格已打印 ({copies}份)"
                elif file_ext in ['.ppt', '.pptx']:
                    app = win32com.client.Dispatch('PowerPoint.Application')
                    app.Visible = False
                    pres = app.Presentations.Open(filepath)
                    for i in range(copies):
                        pres.PrintOut(PrintToFile=False, OutputFileName='', Printer=printer_name)
                        time.sleep(3)
                    pres.Close()
                    app.Quit()
                    return True, f"PowerPoint演示已打印 ({copies}份)"
                return False, "不支持的Office文件类型"
            except Exception as e:
                print(f"COM方案失败: {e}")
                return False, str(e)
        result_holder = [False, ""]
        def run_print():
            result_holder[:] = try_com_print()
        thread = threading.Thread(target=run_print, daemon=True)
        thread.start()
        thread.join(timeout=60)
        if result_holder[0]:
            return result_holder
        try:
            for i in range(copies):
                result = win32api.ShellExecute(0, 'printto', filepath, f'"{printer_name}"', '', win32con.SW_HIDE)
                if result > 32:
                    time.sleep(3)
            return True, f"文档已通过系统PrintTo打印 ({copies}份)"
        except Exception as e:
            print(f"PrintTo方案失败: {e}")
        try:
            result = win32api.ShellExecute(0, 'print', filepath, '', '', win32con.SW_HIDE)
            if result > 32:
                return True, f"文档已使用系统默认方式打印 ({copies}份)"
        except Exception as e:
            print(f"转换方案失败: {e}")
        return False, f"无法打印Office文件: {os.path.basename(filepath)}"
    except Exception as e:
        return False, f"Office打印异常: {str(e)}"


def print_office_com(filepath, printer_name, copies, file_ext):
    """强化Office COM打印 - 支持Microsoft Office和WPS Office"""
    try:
        abs_filepath = os.path.abspath(filepath)
        print(f" 强化Office COM打印: {abs_filepath}")
        if file_ext in ['.doc', '.docx']:
            return _print_word_com(abs_filepath, printer_name, copies)
        elif file_ext in ['.xls', '.xlsx']:
            return _print_excel_com(abs_filepath, printer_name, copies)
        elif file_ext in ['.ppt', '.pptx']:
            return _print_ppt_com(abs_filepath, printer_name, copies)
        else:
            print(" 不支持的Office文档类型")
            return print_file_silent_fallback(filepath, printer_name, copies)
    except Exception as e:
        print(f"Office COM打印整体异常: {e}")
        return False, f"Office COM异常: {str(e)}"


def _print_word_com(abs_filepath, printer_name, copies):
    """Word COM打印 - Microsoft Word + WPS Writer"""
    print(" 强化Word COM打印...")
    print(" 尝试Microsoft Word...")
    ps_script_word = f'''
try {{
    $ErrorActionPreference = "Stop"
    $word = New-Object -ComObject Word.Application
    $word.Visible = $false
    $word.DisplayAlerts = $false
    Write-Host "Microsoft Word COM创建成功"
    $doc = $word.Documents.Open("{abs_filepath.replace(chr(92), chr(92)+chr(92))}")
    Write-Host "Word文档打开成功"
    try {{
        $pageSetup = $doc.Range().PageSetup
        $hasHeader = $false
        $hasFooter = $false
        try {{
            if ($doc.Sections.Count -gt 0) {{
                $section = $doc.Sections.Item(1)
                $headerText = $section.Headers.Item(1).Range.Text
                $footerText = $section.Footers.Item(1).Range.Text
                if ($headerText -and $headerText.Trim().Length -gt 1) {{ $hasHeader = $true }}
                if ($footerText -and $footerText.Trim().Length -gt 1) {{ $hasFooter = $true }}
            }}
        }} catch {{ Write-Host "页眉页脚检测失败: $_" }}
        $optimizedTopMargin = if ($hasHeader) {{ [math]::Max(36, 54) }} else {{ 18 }}
        $optimizedBottomMargin = if ($hasFooter) {{ [math]::Max(36, 54) }} else {{ 18 }}
        $pageSetup.TopMargin = $optimizedTopMargin
        $pageSetup.BottomMargin = $optimizedBottomMargin
        $pageSetup.LeftMargin = 54
        $pageSetup.RightMargin = 54
    }} catch {{ Write-Host "页面设置优化失败: $_" }}
    try {{ $word.ActivePrinter = "{printer_name}" }} catch {{}}
    for ($i = 1; $i -le {copies}; $i++) {{
        try {{
            $doc.PrintOut([ref]$false, [ref]$false, [ref]0, [ref]"", [ref]1, [ref]($doc.Range().End), [ref]7, [ref]1)
            Start-Sleep -Seconds 2
        }} catch {{ Write-Host "Word打印第${{i}}份失败: $_" }}
    }}
    $doc.Close([ref]$false)
    $word.Quit()
    [System.Runtime.Interopservices.Marshal]::ReleaseComObject($doc) | Out-Null
    [System.Runtime.Interopservices.Marshal]::ReleaseComObject($word) | Out-Null
    [System.GC]::Collect()
    Write-Output "Microsoft Word打印成功"
}} catch {{
    Write-Host "Microsoft Word打印失败: $_"
    if ($word) {{ try {{ $word.Quit() }} catch {{}} }}
    exit 1
}}
'''
    try:
        result = subprocess.run(['powershell', '-WindowStyle', 'Hidden', '-Command', ps_script_word],
                              capture_output=True, text=True, timeout=60,
                              creationflags=subprocess.CREATE_NO_WINDOW)
        if result.returncode == 0:
            return True, f"Microsoft Word COM打印完成 ({copies}份)"
        else:
            print(f" Microsoft Word COM失败: {result.stderr[:200] if result.stderr else '无错误信息'}")
    except subprocess.TimeoutExpired:
        print(" Microsoft Word COM超时")
    except Exception as e:
        print(f"Microsoft Word COM异常: {e}")
    # WPS Writer
    print(" 尝试WPS Writer...")
    ps_script_wps = f'''
try {{
    $ErrorActionPreference = "Stop"
    $wps = New-Object -ComObject wps.application
    $wps.Visible = $false
    $wps.DisplayAlerts = $false
    $doc = $null
    try {{
        $doc = $wps.Documents.Open("{abs_filepath.replace(chr(92), chr(92)+chr(92))}")
        try {{
            $pageSetup = $doc.Range().PageSetup
            $pageSetup.TopMargin = 36
            $pageSetup.BottomMargin = 36
            $pageSetup.LeftMargin = 54
            $pageSetup.RightMargin = 54
        }} catch {{}}
        try {{ $wps.ActivePrinter = "{printer_name}" }} catch {{}}
        for ($i = 1; $i -le {copies}; $i++) {{
            try {{ $doc.PrintOut(); Start-Sleep -Seconds 2 }} catch {{}}
        }}
    }} finally {{
        if ($doc) {{ try {{ $doc.Close([ref]$false); [System.Runtime.Interopservices.Marshal]::ReleaseComObject($doc) | Out-Null }} catch {{}} }}
        if ($wps) {{ try {{ $wps.Quit(); [System.Runtime.Interopservices.Marshal]::ReleaseComObject($wps) | Out-Null }} catch {{}} }}
        [System.GC]::Collect()
    }}
    Write-Output "WPS Writer打印成功"
}} catch {{ Write-Host "WPS Writer打印失败: $_"; exit 1 }}
'''
    try:
        result = subprocess.run(['powershell', '-WindowStyle', 'Hidden', '-Command', ps_script_wps],
                              capture_output=True, text=True, timeout=45,
                              creationflags=subprocess.CREATE_NO_WINDOW)
        if result.returncode == 0:
            return True, f"WPS Writer COM打印完成 ({copies}份)"
    except Exception as e:
        print(f"WPS Writer COM异常: {e}")
    print(" Word文档COM打印失败")
    return False, "Word COM对象均不可用"


def _print_excel_com(abs_filepath, printer_name, copies):
    """Excel COM打印 - Microsoft Excel + WPS Spreadsheets"""
    print(" 强化Excel COM打印...")
    print(" 尝试Microsoft Excel...")
    ps_script_excel = f'''
try {{
    $ErrorActionPreference = "Stop"
    $excel = New-Object -ComObject Excel.Application
    $excel.Visible = $false
    $excel.DisplayAlerts = $false
    $workbook = $excel.Workbooks.Open("{abs_filepath.replace(chr(92), chr(92)+chr(92))}")
    try {{
        if ($workbook.Worksheets.Count -gt 0) {{
            $worksheet = $workbook.Worksheets.Item(1)
            $pageSetup = $worksheet.PageSetup
            $pageSetup.TopMargin = $excel.Application.InchesToPoints(0.25)
            $pageSetup.BottomMargin = $excel.Application.InchesToPoints(0.25)
            $pageSetup.LeftMargin = $excel.Application.InchesToPoints(0.75)
            $pageSetup.RightMargin = $excel.Application.InchesToPoints(0.75)
        }}
    }} catch {{}}
    try {{ $excel.ActivePrinter = "{printer_name}" }} catch {{}}
    for ($i = 1; $i -le {copies}; $i++) {{
        try {{
            $workbook.PrintOut([Type]::Missing, [Type]::Missing, 1, [Type]::Missing, [Type]::Missing, [Type]::Missing, [Type]::Missing, [Type]::Missing)
            Start-Sleep -Seconds 2
        }} catch {{}}
    }}
    $workbook.Close([ref]$false)
    $excel.Quit()
    [System.Runtime.Interopservices.Marshal]::ReleaseComObject($workbook) | Out-Null
    [System.Runtime.Interopservices.Marshal]::ReleaseComObject($excel) | Out-Null
    [System.GC]::Collect()
    Write-Output "Microsoft Excel打印成功"
}} catch {{
    if ($excel) {{ try {{ $excel.Quit() }} catch {{}} }}
    exit 1
}}
'''
    try:
        result = subprocess.run(['powershell', '-WindowStyle', 'Hidden', '-Command', ps_script_excel],
                              capture_output=True, text=True, timeout=60,
                              creationflags=subprocess.CREATE_NO_WINDOW)
        if result.returncode == 0:
            return True, f"Microsoft Excel COM打印完成 ({copies}份)"
    except Exception as e:
        print(f"Microsoft Excel COM异常: {e}")
    # WPS Spreadsheets
    print(" 尝试WPS Spreadsheets...")
    ps_script_wps_excel = f'''
try {{
    $ErrorActionPreference = "Stop"
    $et = New-Object -ComObject et.application
    $et.Visible = $false
    $workbook = $et.Workbooks.Open("{abs_filepath.replace(chr(92), chr(92)+chr(92))}")
    try {{
        try {{ $et.ActivePrinter = "{printer_name}" }} catch {{}}
        for ($i = 1; $i -le {copies}; $i++) {{
            try {{ $workbook.PrintOut(); Start-Sleep -Seconds 2 }} catch {{}}
        }}
    }} finally {{
        $workbook.Close([ref]$false)
        $et.Quit()
    }}
    Write-Output "WPS Spreadsheets打印成功"
}} catch {{
    if ($et) {{ try {{ $et.Quit() }} catch {{}} }}
    exit 1
}}
'''
    try:
        result = subprocess.run(['powershell', '-WindowStyle', 'Hidden', '-Command', ps_script_wps_excel],
                              capture_output=True, text=True, timeout=45,
                              creationflags=subprocess.CREATE_NO_WINDOW)
        if result.returncode == 0:
            return True, f"WPS Spreadsheets COM打印完成 ({copies}份)"
    except Exception as e:
        print(f"WPS Spreadsheets COM异常: {e}")
    return False, "Excel COM对象均不可用"


def _print_ppt_com(abs_filepath, printer_name, copies):
    """PowerPoint COM打印 - Microsoft PowerPoint + WPS Presentation"""
    print(" 强化PowerPoint COM打印...")
    print(" 尝试Microsoft PowerPoint...")
    ps_script_ppt = f'''
try {{
    $ErrorActionPreference = "Stop"
    $ppt = New-Object -ComObject PowerPoint.Application
    $ppt.Visible = $false
    $ppt.DisplayAlerts = 0
    $presentation = $ppt.Presentations.Open("{abs_filepath.replace(chr(92), chr(92)+chr(92))}")
    try {{ $ppt.ActivePrinter = "{printer_name}" }} catch {{}}
    for ($i = 1; $i -le {copies}; $i++) {{
        $success = $false
        try {{
            $tempPdf = "$env:TEMP\\ppt_print_${{i}}.pdf"
            $presentation.SaveAs($tempPdf, 32)
            Start-Process -FilePath $tempPdf -Verb PrintTo -ArgumentList "{printer_name}" -WindowStyle Hidden -Wait
            Start-Sleep -Seconds 2
            if (Test-Path $tempPdf) {{ Remove-Item $tempPdf -Force -ErrorAction SilentlyContinue }}
            $success = $true
        }} catch {{}}
        if (-not $success) {{
            try {{ $presentation.PrintOut(); Start-Sleep -Seconds 3 }} catch {{ throw "所有方法失败" }}
        }}
    }}
    $presentation.Close()
    $ppt.Quit()
    [System.Runtime.Interopservices.Marshal]::ReleaseComObject($presentation) | Out-Null
    [System.Runtime.Interopservices.Marshal]::ReleaseComObject($ppt) | Out-Null
    [System.GC]::Collect()
    Write-Output "Microsoft PowerPoint打印成功"
}} catch {{
    if ($ppt) {{ try {{ if ($presentation) {{ $presentation.Close() }}; $ppt.Quit() }} catch {{}} }}
    exit 1
}}
'''
    try:
        result = subprocess.run(['powershell', '-WindowStyle', 'Hidden', '-Command', ps_script_ppt],
                              capture_output=True, text=True, timeout=90,
                              creationflags=subprocess.CREATE_NO_WINDOW)
        if result.returncode == 0:
            return True, f"Microsoft PowerPoint COM打印完成 ({copies}份)"
    except Exception as e:
        print(f"Microsoft PowerPoint COM异常: {e}")
    # WPS Presentation
    print(" 尝试WPS Presentation...")
    ps_script_wps_ppt = f'''
try {{
    $ErrorActionPreference = "Stop"
    $wpp = New-Object -ComObject wpp.application
    $wpp.Visible = $false
    $presentation = $wpp.Presentations.Open("{abs_filepath.replace(chr(92), chr(92)+chr(92))}")
    try {{ $wpp.ActivePrinter = "{printer_name}" }} catch {{}}
    for ($i = 1; $i -le {copies}; $i++) {{
        try {{
            $presentation.PrintOut(); Start-Sleep -Seconds 3
        }} catch {{
            try {{
                $tempPdf = "$env:TEMP\\wps_ppt_temp_${{i}}.pdf"
                $presentation.ExportAsFixedFormat($tempPdf, 2)
                Start-Process -FilePath $tempPdf -Verb PrintTo -ArgumentList "{printer_name}" -WindowStyle Hidden -Wait
                Start-Sleep -Seconds 2
                Remove-Item $tempPdf -Force -ErrorAction SilentlyContinue
            }} catch {{}}
        }}
    }}
    $presentation.Close()
    $wpp.Quit()
    Write-Output "WPS Presentation打印成功"
}} catch {{
    if ($wpp) {{ try {{ $wpp.Quit() }} catch {{}} }}
    exit 1
}}
'''
    try:
        result = subprocess.run(['powershell', '-WindowStyle', 'Hidden', '-Command', ps_script_wps_ppt],
                              capture_output=True, text=True, timeout=75,
                              creationflags=subprocess.CREATE_NO_WINDOW)
        if result.returncode == 0:
            return True, f"WPS Presentation COM打印完成 ({copies}份)"
    except Exception as e:
        print(f"WPS Presentation COM异常: {e}")
    return False, f"""PowerPoint COM打印失败详情：

已尝试的COM方案：
1. Microsoft PowerPoint COM (包含PDF转换备用)
2. WPS Presentation COM (包含PDF转换备用)

可能原因：
- PowerPoint/WPS未正确安装或注册
- COM对象权限不足
- 文档格式损坏或不兼容
- 打印机驱动问题

建议解决方案：
1. 手动打开 {os.path.basename(abs_filepath)} 测试是否正常
2. 尝试"打印到PDF"测试COM功能
3. 重新注册Office COM: regsvr32 /i pptcore.dll
4. 以管理员权限运行打印服务"""


def print_html_silent(filepath, printer_name, copies=1):
    """专门用于HTML文件的静默打印"""
    try:
        for i in range(copies):
            cmd = ['rundll32.exe', 'mshtml.dll,PrintHTML', filepath]
            subprocess.run(cmd, creationflags=subprocess.CREATE_NO_WINDOW)
        return True, f"HTML静默打印已发送到 {printer_name} ({copies}份)"
    except Exception as e1:
        try:
            ps_script = f'''
try {{
    $ie = New-Object -ComObject InternetExplorer.Application
    $ie.Visible = $false
    $ie.Navigate("file:///{filepath.replace(chr(92), '/')}")
    while ($ie.Busy) {{ Start-Sleep -Milliseconds 100 }}
    for ($i = 1; $i -le {copies}; $i++) {{ $ie.ExecWB(6, 2) }}
    $ie.Quit()
}} catch {{ Write-Host "HTML打印失败： $_" }}
'''
            subprocess.run(['powershell', '-WindowStyle', 'Hidden', '-Command', ps_script],
                          creationflags=subprocess.CREATE_NO_WINDOW)
            return True, f"HTML PowerShell静默打印已执行 ({copies}份)"
        except Exception as e2:
            return print_file_silent_fallback(filepath, printer_name, copies)


def print_file_with_settings(filepath, printer_name, copies=1, duplex=1, papersize='A4', quality='normal'):
    """使用获取到的真实打印设置进行打印 - 总入口"""
    saved_duplex = None
    try:
        try:
            ensure_printer_connection(printer_name)
        except Exception:
            pass
        print(f"开始打印文件: {filepath}")
        print(f"目标打印机: {printer_name}")
        print(f"打印份数: {copies}")
        file_ext = os.path.splitext(filepath)[1].lower()
        if duplex > 1:
            saved_duplex = apply_printer_duplex_setting(printer_name, duplex)
            if saved_duplex is not None:
                time.sleep(0.5)
        def try_native_print():
            try:
                devmode = apply_printer_settings(printer_name, copies, duplex, papersize, quality)
                if devmode is None:
                    return False
                printer_handle = win32print.OpenPrinter(printer_name)
                try:
                    doc_info = {'pDocName': os.path.basename(filepath), 'pOutputFile': None, 'pDatatype': None}
                    win32print.StartDocPrinter(printer_handle, 1, doc_info)
                    win32print.StartPagePrinter(printer_handle)
                    with open(filepath, 'rb') as f:
                        win32print.WritePrinter(printer_handle, f.read())
                    win32print.EndPagePrinter(printer_handle)
                    win32print.EndDocPrinter(printer_handle)
                    return True
                finally:
                    win32print.ClosePrinter(printer_handle)
            except Exception as e:
                print(f"原生打印失败: {e}")
                return False
        if file_ext in ['.pdf', '.txt', '.jpg', '.jpeg', '.png', '.bmp', '.gif']:
            if try_native_print():
                return True
        if file_ext == '.pdf':
            return print_pdf_with_settings(filepath, printer_name, copies, duplex, papersize, quality)
        elif file_ext in ['.jpg', '.jpeg', '.png', '.bmp', '.gif']:
            return print_image_silent(filepath, printer_name, copies)
        elif file_ext in ['.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx']:
            return print_office_silent(filepath, printer_name, copies)
        elif file_ext == '.txt':
            return print_text_file_simple(filepath, printer_name, copies)
        else:
            return print_with_shell_execute(filepath, printer_name, copies)
    except Exception as e:
        print(f"打印操作失败: {e}")
        return print_file_silent_fallback(filepath, printer_name, copies)
    finally:
        if saved_duplex is not None:
            time.sleep(1)
            restore_printer_duplex_setting(printer_name, saved_duplex)
