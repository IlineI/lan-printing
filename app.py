#!/usr/bin/env python
# -*- coding: utf-8 -*-
#作者：忆痕
#仓库地址：https://github.com/a937750307/lan-printing

"""Flask应用、路由注册、API端点"""

import os
import sys
import io
import math
import time
import json
import threading
import subprocess
import tempfile
from datetime import datetime

from flask import (Flask, render_template, request, redirect, url_for,
                   flash, jsonify, send_from_directory, send_file, abort)
from flask_cors import CORS

from modules import config
from modules.config import (DEVICE_STATUS, CONSOLE_WINDOW, CONSOLE_VISIBLE,
                    VIRTUAL_PRINTERS, ALLOWED_EXT, DEBUG_MODE,
                    load_config, save_config, get_config_port, save_port_config, init_paths,
                    setup_logger, logger)
from modules.path_manager import path_manager
from modules.printer_manager import (PRINTERS, ALL_PRINTERS, printer_cache,
                             get_default_printer, refresh_printer_list,
                             is_physical_printer, get_printer_capabilities,
                             get_print_queue_jobs, cancel_print_jobs_by_document,
                             clear_all_print_queues)
from modules.scanner_manager import (get_available_scanners, cleanup_port_and_restart_wia,
                             force_release_wia_device, start_scan_silent)
from modules.print_engine import (print_file_with_settings, print_pdf_silent,
                          print_image_silent, print_office_silent,
                          print_text_file_simple)
from modules.file_manager import (allowed_file, get_client_info, log_print, log_scan,
                          get_scanned_files, get_file_list, get_logs,
                          format_file_size, clean_old_logs, clean_old_logs_by_date, clean_old_files)
from modules.service_manager import service_manager, monitor_service_health, run_flask, run_wsgi
from modules.tray import (setup_tray, check_admin_privileges, check_windows_features,
                  show_error_dialog, auto_clear_console, hide_console)
from modules.network import get_local_ip, get_external_ip, detect_network_mode

# ===== Flask 应用初始化 =====
app = Flask(__name__, template_folder='templates', static_folder=None)

# secret_key: 从配置文件读取，或随机生成
import secrets
try:
    _cfg = load_config()
    app.secret_key = _cfg.get('secret_key') or secrets.token_hex(32)
except Exception:
    app.secret_key = secrets.token_hex(32)

# 启用 CORS（局域网服务，允许所有来源）
CORS(app)

# ==================== 初始化路径 ====================
init_paths(path_manager)
setup_logger(path_manager)


# ===== 静态文件路由 =====
@app.route('/static/<path:filename>')
def serve_static(filename):
    """提供静态文件服务 - Bootstrap CSS 和 JS"""
    if '..' in filename or filename.startswith('/'):
        abort(403)
    allowed_files = {'bootstrap.min.css', 'bootstrap.bundle.min.js'}
    # 允许自定义CSS/JS子目录
    if filename not in allowed_files and not filename.startswith('css/') and not filename.startswith('js/'):
        abort(403)
    # 在 static/ 子目录下查找文件
    file_path = path_manager.get_resource_path(os.path.join('static', filename))
    if not os.path.exists(file_path):
        file_path = os.path.join(os.getcwd(), 'static', filename)
        if not os.path.exists(file_path):
            # 兼容旧版：直接在资源目录查找（Bootstrap文件）
            file_path = path_manager.get_resource_path(filename)
            if not os.path.exists(file_path):
                file_path = os.path.join(os.getcwd(), filename)
                if not os.path.exists(file_path):
                    abort(404)
    try:
        if filename.endswith('.css'):
            response = send_file(file_path, mimetype='text/css')
        elif filename.endswith('.js'):
            response = send_file(file_path, mimetype='application/javascript')
        else:
            response = send_file(file_path)
        if response:
            response.cache_control.max_age = 3600
        return response
    except Exception as e:
        print(f"静态文件服务错误 ({filename}): {e}")
        abort(500)


# ===== Flask 配置 =====
def get_flask_config():
    return {
        'MAX_CONTENT_LENGTH': 100 * 1024 * 1024,
        'PERMANENT_SESSION_LIFETIME': 3600,
        'TEMPLATES_AUTO_RELOAD': False,
        'JSON_AS_ASCII': False,
        'JSONIFY_PRETTYPRINT_REGULAR': False,
        'SEND_FILE_MAX_AGE_DEFAULT': 300,
    }

app.config.update(get_flask_config())
path_manager.ensure_data_dirs()


# ===== 请求后钩子 =====
@app.after_request
def after_request(response):
    """请求处理后的清理工作"""
    try:
        if not hasattr(app, 'request_count'):
            app.request_count = 0
        app.request_count += 1
        if app.request_count % 500 == 0:
            import gc
            collected = gc.collect()
            if app.request_count > 10000:
                app.request_count = 0
        response.headers.update({
            'Cache-Control': 'no-cache, no-store, must-revalidate',
            'Pragma': 'no-cache',
            'Expires': '0',
            'X-Content-Type-Options': 'nosniff',
            'X-Frame-Options': 'DENY'
        })
        if request.method in ['POST', 'PUT', 'DELETE']:
            response.headers['Connection'] = 'close'
    except Exception as e:
        print(f" 请求后清理异常: {e}")
    return response


# ===== 错误处理器 =====
@app.errorhandler(500)
def internal_error(error):
    return jsonify({'error': '服务器内部错误', 'message': '请稍后重试'}), 500

@app.errorhandler(413)
def too_large(error):
    return jsonify({'error': '文件过大', 'message': '上传文件大小不能超过100MB'}), 413


# ===== 健康检查 =====
@app.route('/health', methods=['GET'])
def health():
    try:
        service_manager.update_health_check()
        uptime = 0
        if hasattr(service_manager, 'start_time') and service_manager.start_time:
            uptime = time.time() - service_manager.start_time
        status = {
            'status': 'ok',
            'time': int(time.time()),
            'service_running': getattr(service_manager, 'service_running', False),
            'uptime': int(uptime)
        }
        resp = jsonify(status)
        return resp
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)}), 500


# ===== 扫描仪API =====
@app.route('/api/scanners', methods=['GET'])
def api_list_scanners():
    try:
        scanners = get_available_scanners()
        out = [{'name': str(s.get('name')), 'id': str(s.get('id')),
                'type': str(s.get('type')), 'available': bool(s.get('available', False))}
               for s in scanners]
        resp = jsonify({'status': 'success', 'count': len(out), 'scanners': out, 'timestamp': int(time.time())})
        resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        return resp
    except Exception as e:
        return jsonify({'status': 'error', 'error': '扫描仪列表获取失败', 'detail': str(e)}), 500


@app.route('/api/release_scanner', methods=['POST'])
def api_release_scanner():
    try:
        print("执行强制释放扫描仪设备...")
        try:
            port = getattr(app, 'current_port', 5000)
            cleanup_port_and_restart_wia(port)
        except Exception as e:
            print(f"[WARN] 端口清理异常: {e}")
        success = force_release_wia_device()
        if DEVICE_STATUS['is_scanning']:
            DEVICE_STATUS['is_scanning'] = False
            DEVICE_STATUS['scan_start_time'] = None
            DEVICE_STATUS['scan_client'] = ''
        if success:
            return jsonify({'status': 'success', 'message': '扫描仪设备已成功释放', 'timestamp': int(time.time())})
        else:
            return jsonify({'status': 'error', 'error': '释放失败'}), 500
    except Exception as e:
        return jsonify({'status': 'error', 'error': '操作异常', 'detail': str(e)}), 500


@app.route('/api/scan', methods=['POST'])
def api_trigger_scan():
    """触发扫描操作 - 支持内网穿透"""
    try:
        data = request.get_json() or {}
        scanner_id = data.get('scanner_id', 'default')
        scanner_name = data.get('scanner_name', '通用扫描')
        scan_format = data.get('format', 'PNG').upper()
        client_ip = request.headers.get('X-Forwarded-For', '').split(',')[0].strip() or request.remote_addr
        allowed_formats = ('PNG', 'JPG', 'JPEG', 'BMP', 'TIFF')
        if scan_format not in allowed_formats:
            return jsonify({'status': 'error', 'error': '不支持的扫描格式', 'client_ip': client_ip}), 400
        if DEVICE_STATUS.get('is_scanning'):
            return jsonify({'status': 'error', 'error': '扫描器正在忙碌中', 'client_ip': client_ip}), 409
        DEVICE_STATUS['is_scanning'] = True
        DEVICE_STATUS['scan_start_time'] = time.time()
        DEVICE_STATUS['scan_client'] = client_ip
        try:
            ok, message = start_scan_silent(scanner_id, scanner_name, scan_format)
            scan_time = int(time.time() - DEVICE_STATUS['scan_start_time'])
            resp = jsonify({
                'status': 'success' if ok else 'warning', 'success': ok,
                'message': message, 'scan_time': scan_time,
                'client_ip': client_ip, 'timestamp': int(time.time())
            })
            return resp, (200 if ok else 206)
        finally:
            DEVICE_STATUS['is_scanning'] = False
            DEVICE_STATUS['scan_start_time'] = None
            DEVICE_STATUS['scan_client'] = ''
    except Exception as e:
        error_msg = str(e)
        if 'WIA' in error_msg or 'busy' in error_msg.lower():
            try:
                force_release_wia_device()
                error_msg += "\n(已尝试自动释放设备，请重试)"
            except:
                pass
        return jsonify({'status': 'error', 'error': '触发扫描失败', 'detail': error_msg}), 500


# ===== 打印机信息API =====
@app.route('/api/printer_info')
def get_printer_info_api():
    try:
        printer_name = request.args.get('printer')
        if not printer_name:
            return jsonify({'success': False, 'error': '未指定打印机名称'})
        capabilities = get_printer_capabilities(printer_name)
        return jsonify({'success': True, 'capabilities': capabilities})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/refresh_printers')
def refresh_printers_api():
    try:
        success = refresh_printer_list()
        if success:
            default_printer = get_default_printer()
            return jsonify({'success': True, 'printers': PRINTERS, 'default_printer': default_printer,
                           'message': f'已刷新，检测到 {len(PRINTERS)} 台物理打印机'})
        else:
            return jsonify({'success': False, 'error': '刷新打印机列表失败'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


# ===== 文件管理API =====
@app.route('/api/delete_file', methods=['POST'])
def delete_file_api():
    try:
        try:
            data = request.get_json()
        except Exception as json_error:
            return jsonify({'success': False, 'error': f'JSON解析错误: {str(json_error)}'})
        if not data or 'filename' not in data:
            return jsonify({'success': False, 'error': '未提供文件名'})
        filename = data['filename']
        filepath = os.path.join(config.UPLOAD_FOLDER, filename)
        if not os.path.exists(filepath):
            return jsonify({'success': False, 'error': '文件不存在或已被删除'})
        cancel_result = {'cancelled': [], 'skipped': [], 'total_found': 0}
        try:
            force_cancel = request.get_json().get('force_cancel_active', False) if request.get_json() else False
            cancel_result = cancel_print_jobs_by_document(filename, cancel_active=force_cancel)
        except Exception as cancel_error:
            print(f" 取消打印任务失败: {cancel_error}")
        os.remove(filepath)
        try:
            client_ip = request.remote_addr or '未知IP'
            cancelled_count = len(cancel_result['cancelled'])
            cancelled_info = f", 取消了 {cancelled_count} 个打印任务" if cancelled_count > 0 else ""
            logger.info(f"客户端: {client_ip} 删除文件: {filename}{cancelled_info}")
        except:
            pass
        response_message = f'文件 {filename} 已删除'
        cancelled_count = len(cancel_result['cancelled'])
        skipped_count = len(cancel_result['skipped'])
        if cancelled_count > 0:
            response_message += f'，取消了 {cancelled_count} 个打印任务'
        return jsonify({'success': True, 'message': response_message,
                       'print_queue_result': {'cancelled_jobs': cancelled_count,
                       'skipped_jobs': skipped_count, 'total_found': cancel_result['total_found']}})
    except Exception as e:
        return jsonify({'success': False, 'error': f'服务器错误: {str(e)}'})


@app.route('/api/delete_all_files', methods=['POST'])
def delete_all_files_api():
    try:
        files = os.listdir(config.UPLOAD_FOLDER)
        deleted_count = 0
        cleared_jobs = 0
        try:
            cleared_jobs = clear_all_print_queues()
        except:
            pass
        for filename in files:
            try:
                filepath = os.path.join(config.UPLOAD_FOLDER, filename)
                if os.path.isfile(filepath):
                    os.remove(filepath)
                    deleted_count += 1
            except:
                pass
        try:
            client_ip = request.remote_addr or '未知IP'
            logger.info(f"客户端: {client_ip} 清空队列: 删除了 {deleted_count} 个文件")
        except:
            pass
        return jsonify({'success': True, 'count': deleted_count, 'cleared_jobs': cleared_jobs,
                       'message': f'已删除 {deleted_count} 个文件'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


# ===== 扫描功能路由 =====
@app.route('/api/get_scanners')
def get_scanners():
    try:
        scanners = get_available_scanners()
        return jsonify({'success': True, 'scanners': scanners, 'count': len(scanners)})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/device_status')
def get_device_status():
    current_time = time.time()
    if DEVICE_STATUS['is_printing'] and DEVICE_STATUS['print_start_time']:
        if current_time - DEVICE_STATUS['print_start_time'] > 30:
            DEVICE_STATUS['is_printing'] = False
            DEVICE_STATUS['print_start_time'] = None
            DEVICE_STATUS['print_client'] = ''
    if DEVICE_STATUS['is_scanning'] and DEVICE_STATUS['scan_start_time']:
        if current_time - DEVICE_STATUS['scan_start_time'] > 60:
            DEVICE_STATUS['is_scanning'] = False
            DEVICE_STATUS['scan_start_time'] = None
            DEVICE_STATUS['scan_client'] = ''
    print_duration = int(current_time - DEVICE_STATUS['print_start_time']) if DEVICE_STATUS['is_printing'] and DEVICE_STATUS['print_start_time'] else 0
    scan_duration = int(current_time - DEVICE_STATUS['scan_start_time']) if DEVICE_STATUS['is_scanning'] and DEVICE_STATUS['scan_start_time'] else 0
    return jsonify({
        'success': True, 'is_printing': DEVICE_STATUS['is_printing'],
        'is_scanning': DEVICE_STATUS['is_scanning'],
        'print_duration': print_duration, 'scan_duration': scan_duration,
        'print_client': DEVICE_STATUS['print_client'], 'scan_client': DEVICE_STATUS['scan_client']
    })


# ===== 扫描文件管理API =====
@app.route('/api/scanned_files')
def get_scanned_files_api():
    try:
        files = get_scanned_files(path_manager)
        return jsonify({'success': True, 'files': files, 'count': len(files)})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/scanned_files/<filename>')
def download_scanned_file(filename):
    try:
        scan_folder = path_manager.get_scan_dir()
        if '/' in filename or '\\' in filename or '..' in filename:
            return jsonify({'error': '非法文件名'}), 400
        file_path = os.path.join(scan_folder, filename)
        if not os.path.exists(file_path):
            return jsonify({'error': '文件不存在'}), 404
        file_ext = os.path.splitext(filename)[1].lower()
        if file_ext == '.pdf':
            return send_from_directory(scan_folder, filename, as_attachment=True, mimetype='application/pdf')
        else:
            return send_from_directory(scan_folder, filename, as_attachment=True)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/scanned_files/<filename>/preview')
def preview_scanned_file(filename):
    try:
        scan_folder = path_manager.get_scan_dir()
        if '/' in filename or '\\' in filename or '..' in filename:
            return jsonify({'error': '非法文件名'}), 400
        file_path = os.path.join(scan_folder, filename)
        if not os.path.exists(file_path):
            return jsonify({'error': '文件不存在'}), 404
        file_ext = os.path.splitext(filename)[1].lower()
        if file_ext not in ['.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.tif']:
            return jsonify({'error': '该文件类型不支持预览'}), 400
        return send_from_directory(scan_folder, filename)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/scanned_files/<filename>/print', methods=['POST'])
def print_scanned_file(filename):
    try:
        scan_folder = path_manager.get_scan_dir()
        if '/' in filename or '\\' in filename or '..' in filename:
            return jsonify({'success': False, 'error': '非法文件名'})
        file_path = os.path.join(scan_folder, filename)
        if not os.path.exists(file_path):
            return jsonify({'success': False, 'error': '文件不存在'})
        printer_name = request.json.get('printer', get_default_printer())
        copies = int(request.json.get('copies', 1))
        client_info = get_client_info()
        success = print_file_with_settings(file_path, printer_name, copies)
        if success:
            logger.info(f"客户端: {client_info} 打印扫描文件: {filename} -> {printer_name}")
            return jsonify({'success': True, 'message': f"扫描文件 {filename} 已发送"})
        else:
            return jsonify({'success': False, 'error': '打印失败'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/scanned_files/<filename>/delete', methods=['DELETE'])
def delete_scanned_file(filename):
    try:
        scan_folder = path_manager.get_scan_dir()
        if '/' in filename or '\\' in filename or '..' in filename:
            return jsonify({'success': False, 'error': '非法文件名'})
        file_path = os.path.join(scan_folder, filename)
        if not os.path.exists(file_path):
            return jsonify({'success': False, 'error': '文件不存在'})
        os.remove(file_path)
        client_info = get_client_info()
        logger.info(f"客户端: {client_info} 删除扫描文件: {filename}")
        return jsonify({'success': True, 'message': f'文件 {filename} 已删除'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/clear_scanned_files', methods=['POST'])
def clear_all_scanned_files():
    try:
        scan_folder = path_manager.get_scan_dir()
        if not os.path.exists(scan_folder):
            return jsonify({'status': 'success', 'deleted_count': 0})
        deleted_count = 0
        for filename in os.listdir(scan_folder):
            file_path = os.path.join(scan_folder, filename)
            if os.path.isfile(file_path):
                try:
                    os.remove(file_path)
                    deleted_count += 1
                except:
                    pass
        client_info = get_client_info()
        logger.info(f"客户端: {client_info} 清空扫描队列")
        return jsonify({'status': 'success', 'deleted_count': deleted_count})
    except Exception as e:
        return jsonify({'status': 'error', 'error': str(e)}), 500


# ===== 打印队列API =====
@app.route('/api/print_queue', methods=['GET'])
def get_print_queue_api():
    try:
        printer_name = request.args.get('printer')
        jobs = get_print_queue_jobs(printer_name)
        return jsonify({'success': True, 'jobs': jobs, 'count': len(jobs)})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/clear_print_queue', methods=['POST'])
def clear_print_queue_api():
    try:
        data = request.get_json() or {}
        printer_name = data.get('printer')
        cleared_count = 0
        if printer_name:
            jobs = get_print_queue_jobs(printer_name)
            for job in jobs:
                try:
                    import win32print
                    printer_handle = win32print.OpenPrinter(printer_name)
                    win32print.SetJob(printer_handle, job['job_id'], 0, None, win32print.JOB_CONTROL_CANCEL)
                    win32print.ClosePrinter(printer_handle)
                    cleared_count += 1
                except:
                    pass
            message = f'已清空打印机 {printer_name} 的 {cleared_count} 个任务'
        else:
            cleared_count = clear_all_print_queues()
            message = f'已清空所有打印机的 {cleared_count} 个任务'
        if cleared_count > 0 and DEVICE_STATUS['is_printing']:
            DEVICE_STATUS['is_printing'] = False
            DEVICE_STATUS['print_start_time'] = None
            DEVICE_STATUS['print_client'] = ''
            try:
                port = getattr(app, 'current_port', 5000)
                cleanup_port_and_restart_wia(port)
            except:
                pass
            try:
                force_release_wia_device()
            except:
                pass
        try:
            client_ip = request.remote_addr or '未知IP'
            logger.info(f"客户端: {client_ip} 清空打印队列: {message}")
        except:
            pass
        return jsonify({'success': True, 'cleared_count': cleared_count, 'message': message})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


# ===== 主页面路由 =====
@app.route('/', methods=['GET', 'POST'])
def upload_file():
    files = get_file_list()
    logs = get_logs()
    env_status = None
    printer_caps = {}
    if PRINTERS:
        printer_caps = get_printer_capabilities(PRINTERS[0])
    else:
        printer_caps = {
            'duplex_support': False, 'color_support': False,
            'paper_sizes': ['A4', 'A3', 'Letter'],
            'quality_levels': ['normal'],
            'printer_status': '无可用打印机', 'driver_name': '未知'
        }
    if request.method == 'POST':
        try:
            if DEVICE_STATUS['is_scanning']:
                scan_duration = int(time.time() - DEVICE_STATUS['scan_start_time']) if DEVICE_STATUS['scan_start_time'] else 0
                flash(f" 设备正在扫描中\n\n正在扫描: {scan_duration}秒", "danger")
                return redirect(url_for('upload_file'))
            if DEVICE_STATUS['is_printing']:
                print_duration = int(time.time() - DEVICE_STATUS['print_start_time']) if DEVICE_STATUS['print_start_time'] else 0
                flash(f" 设备正在打印中\n\n正在打印: {print_duration}秒", "warning")
                return redirect(url_for('upload_file'))
            client_info = get_client_info()
            printer = request.form.get('printer')
            copies = int(request.form.get('copies', 1))
            duplex = int(request.form.get('duplex', 1))
            papersize = request.form.get('papersize', '9')
            quality = request.form.get('quality', '600x600')
            uploaded_files = request.files.getlist('file')
            DEVICE_STATUS['is_printing'] = True
            DEVICE_STATUS['print_start_time'] = time.time()
            DEVICE_STATUS['print_client'] = client_info
            if not uploaded_files or all(not f.filename for f in uploaded_files):
                flash(" 错误: 请选择要打印的文件！", "danger")
                return redirect(url_for('upload_file'))
            if not printer or printer == "" or printer == "未检测到可用打印机":
                flash(" 错误: 未选择有效的打印机！", "danger")
                return redirect(url_for('upload_file'))
            if not is_physical_printer(printer):
                flash(f" 警告: '{printer}' 是虚拟打印机!", "warning")
            success_count = 0
            total_files = 0
            for f in uploaded_files:
                if f and f.filename and allowed_file(f.filename):
                    total_files += 1
                    filename = f.filename
                    filepath = os.path.join(config.UPLOAD_FOLDER, filename)
                    counter = 1
                    original_filename = filename
                    while os.path.exists(filepath) and counter <= 100:
                        name, ext = os.path.splitext(original_filename)
                        filename = f"{name}_{counter}{ext}"
                        filepath = os.path.join(config.UPLOAD_FOLDER, filename)
                        counter += 1
                    if counter > 100:
                        flash(f" 文件 {original_filename} 名称冲突！", "danger")
                        continue
                    try:
                        f.save(filepath)
                        if not os.path.exists(filepath) or os.path.getsize(filepath) == 0:
                            flash(f" 文件 {filename} 保存失败！", "danger")
                            continue
                        file_ext = os.path.splitext(filepath)[1].lower()
                        result = None
                        if file_ext == '.pdf':
                            result = print_pdf_silent(filepath, printer, copies)
                        elif file_ext in ['.jpg', '.jpeg', '.png', '.bmp', '.gif']:
                            result = print_image_silent(filepath, printer, copies)
                        elif file_ext in ['.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx']:
                            result = print_office_silent(filepath, printer, copies)
                        elif file_ext == '.txt':
                            result = print_text_file_simple(filepath, printer, copies)
                        else:
                            result = print_file_with_settings(filepath, printer, copies, duplex, papersize, quality)
                        if result and len(result) >= 2:
                            success, message = result[0], result[1]
                        elif result is True:
                            success, message = True, "打印任务已发送"
                        elif result is False:
                            success, message = False, "打印失败"
                        else:
                            success, message = False, "未知错误"
                        if success:
                            success_count += 1
                            flash(f" {filename} {message}", "success")
                            log_print(filename, printer, copies, duplex, papersize, quality, client_info)
                        else:
                            flash(f" {filename} 打印失败: {message}", "danger")
                            log_print(f"{filename} 失败: {message}", printer, copies, duplex, papersize, quality, client_info)
                    except Exception as e:
                        flash(f" {filename} 打印异常: {str(e)}", "danger")
                        log_print(f"{filename} {str(e)}", printer, copies, duplex, papersize, quality, client_info)
                elif f and f.filename:
                    flash(f" 文件 {f.filename} 格式不支持", "warning")
            if total_files > 0:
                if success_count == total_files:
                    flash(f" 所有文件({success_count}/{total_files})都已成功发送！", "success")
                elif success_count > 0:
                    flash(f" 部分文件打印成功({success_count}/{total_files})", "warning")
                else:
                    flash(f" 所有文件打印都失败", "danger")
            else:
                flash(" 未找到有效的文件", "danger")
        except Exception as e:
            flash(f" 请求处理异常: {str(e)}", "danger")
        finally:
            DEVICE_STATUS['is_printing'] = False
            DEVICE_STATUS['print_start_time'] = None
            DEVICE_STATUS['print_client'] = ''
        return redirect(url_for('upload_file'))
    default_printer = get_default_printer()
    current_port = getattr(app, 'current_port', 5000)
    config_port = get_config_port()
    port_from_config = (current_port == config_port)
    return render_template('index.html', printers=PRINTERS, files=files, logs=logs,
                          printer_caps=printer_caps, default_printer=default_printer,
                          env_status=env_status, current_port=current_port,
                          port_from_config=port_from_config)


# ===== 文件预览和下载 =====
@app.route('/preview/<filename>')
def preview_file(filename):
    fpath = os.path.join(config.UPLOAD_FOLDER, filename)
    if not os.path.exists(fpath):
        return f'<div class="container mt-4"><div class="alert alert-danger"><h4>文件未找到</h4><p>文件 "{filename}" 不存在或已被删除！</p><p><a href="/" class="btn btn-primary">返回首页</a></p></div></div>', 404
    try:
        ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
        if ext in {'jpg', 'jpeg', 'png'}:
            return send_from_directory(config.UPLOAD_FOLDER, filename, mimetype=f'image/{ext}')
        elif ext == 'pdf':
            return send_from_directory(config.UPLOAD_FOLDER, filename, mimetype='application/pdf')
        elif ext == 'txt':
            try:
                with open(fpath, 'r', encoding='utf-8') as fh:
                    content = fh.read()
            except UnicodeDecodeError:
                with open(fpath, 'r', encoding='gbk') as fh:
                    content = fh.read()
            return f'<div class="container mt-4"><div class="card"><div class="card-body"><pre style="white-space: pre-wrap; font-family: monospace;">{content}</pre></div></div></div>'
        else:
            file_size = os.path.getsize(fpath)
            size_str = f"{file_size} B" if file_size < 1024 else f"{file_size / 1024:.1f} KB" if file_size < 1024 * 1024 else f"{file_size / (1024 * 1024):.1f} MB"
            return f'<div class="container mt-4"><div class="card"><div class="card-body"><h5>{filename}</h5><p>大小: {size_str}</p><a href="/uploads/{filename}" class="btn btn-primary" download>下载</a></div></div></div>'
    except Exception as e:
        return f'<div class="container mt-4"><div class="alert alert-danger"><h4>预览错误</h4><p>{str(e)}</p></div></div>', 500


@app.route('/uploads/<filename>')
def download_file(filename):
    """提供文件下载"""
    return send_from_directory(config.UPLOAD_FOLDER, filename, as_attachment=True)


# ==================== 主程序入口 ====================
if __name__ == '__main__':
    from modules.launcher import launch
    launch(app)
