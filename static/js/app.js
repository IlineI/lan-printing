// 获取设备名并设置到请求头
function getDeviceName() {
    let deviceName = '';
    
    // 尝试多种方法获取设备名
    try {
        // 方法1: 尝试获取网络信息中的主机名 (某些浏览器支持)
        if (navigator.connection && navigator.connection.effectiveType) {
            // 现代浏览器可能提供网络信息
        }
        
        // 方法2: 从User Agent解析设备信息
        const ua = navigator.userAgent;
        
        // Android设备
        if (/Android/i.test(ua)) {
            const match = ua.match(/Android.*?;\s*([^)]+)/);
            if (match) {
                deviceName = match[1].trim();
            } else {
                deviceName = 'Android设备';
            }
        }
        // iOS设备
        else if (/iPhone/i.test(ua)) {
            deviceName = 'iPhone';
        }
        else if (/iPad/i.test(ua)) {
            deviceName = 'iPad';
        }
        // Windows设备
        else if (/Windows/i.test(ua)) {
            const winMatch = ua.match(/Windows NT ([\d.]+)/);
            if (winMatch) {
                const version = winMatch[1];
                const versionNames = {
                    '10.0': 'Win10/11电脑',
                    '6.3': 'Win8.1电脑',
                    '6.2': 'Win8电脑',
                    '6.1': 'Win7电脑'
                };
                deviceName = versionNames[version] || `Windows NT ${version}电脑`;
            } else {
                deviceName = 'Windows电脑';
            }
        }
        // Mac设备
        else if (/Mac|Macintosh/i.test(ua)) {
            const macMatch = ua.match(/Mac OS X ([\d_]+)/);
            if (macMatch) {
                const version = macMatch[1].replace(/_/g, '.');
                deviceName = `macOS ${version}`;
            } else {
                deviceName = 'Mac电脑';
            }
        }
        // Linux设备
        else if (/Linux/i.test(ua)) {
            deviceName = 'Linux电脑';
        }
        else {
            deviceName = '未知设备';
        }
    } catch (e) {
        deviceName = '设备信息获取失败';
    }
    
    return deviceName;
}

// 为AJAX请求添加设备名 (用于删除操作等)
function addDeviceNameToRequests() {
    const deviceName = encodeURIComponent(getDeviceName());
    
    // 拦截fetch请求
    const originalFetch = window.fetch;
    window.fetch = function(url, options = {}) {
        options.headers = options.headers || {};
        options.headers['X-Device-Name'] = deviceName;
        return originalFetch(url, options);
    };
}

// 简化的警告消息处理
document.addEventListener('DOMContentLoaded', function() {
    // 初始化AJAX请求拦截
    addDeviceNameToRequests();
    
    // 设置设备名到隐藏字段
    const deviceNameField = document.getElementById('deviceNameField');
    if (deviceNameField) {
        deviceNameField.value = getDeviceName();
    }
    
    // 为表单提交添加设备名
    const printForm = document.getElementById('printForm');
    if (printForm) {
        printForm.addEventListener('submit', function() {
            const deviceNameField = document.getElementById('deviceNameField');
            if (deviceNameField) {
                deviceNameField.value = getDeviceName();
            }
        });
    }
    
    // 警告消息自动关闭功能
    const alerts = document.querySelectorAll('.alert');
    alerts.forEach(alert => {
        const closeBtn = alert.querySelector('.btn-close');
        if (closeBtn) {
            closeBtn.addEventListener('click', function() {
                alert.style.display = 'none';
            });
        }
        
        // 5秒后自动关闭成功消息
        if (alert.classList.contains('alert-success')) {
            setTimeout(() => {
                alert.style.display = 'none';
            }, 5000);
        }
    });
});

// 根据所选打印机实时获取并填充分辨率与纸张列表
function refreshPrinterInfo() {
    const printerSelect = document.getElementById('printerSelect');
    const paperSelect = document.getElementById('paperSelect');
    const qualitySelect = document.getElementById('qualitySelect');
    if (!printerSelect) return;
    const selectedPrinter = printerSelect.value;
    if (!selectedPrinter) return;

    fetch('/api/printer_info?printer=' + encodeURIComponent(selectedPrinter))
        .then(r => r.json())
        .then(data => {
            if (!data.success) return;
            const caps = data.capabilities || {};
            // 填充纸张
            if (paperSelect) {
                const prev = paperSelect.value;
                paperSelect.innerHTML = '';
                if (caps.papers && caps.papers.length) {
                    let a4Index = -1;
                    caps.papers.forEach((p, idx) => {
                        const opt = document.createElement('option');
                        opt.value = p.id;
                        opt.textContent = p.name;
                        paperSelect.appendChild(opt);
                        if (p.id === 9 || (typeof p.name === 'string' && p.name.toUpperCase().includes('A4'))) {
                            a4Index = idx;
                        }
                    });
                    // 优先恢复之前选择；否则默认选A4；否则选第一项
                    if (prev && Array.from(paperSelect.options).some(o => String(o.value) === String(prev))) {
                        paperSelect.value = prev;
                    } else if (a4Index >= 0) {
                        paperSelect.selectedIndex = a4Index;
                    } else {
                        paperSelect.selectedIndex = 0;
                    }
                } else {
                    const opt = document.createElement('option');
                    opt.value = '9'; // A4 ID
                    opt.textContent = 'A4';
                    paperSelect.appendChild(opt);
                }
            }
            // 填充分辨率
            if (qualitySelect) {
                qualitySelect.innerHTML = '';
                if (caps.resolutions && caps.resolutions.length) {
                    caps.resolutions.forEach(r => {
                        const opt = document.createElement('option');
                        opt.value = r;
                        opt.textContent = r;
                        qualitySelect.appendChild(opt);
                    });
                } else {
                    const opt = document.createElement('option');
                    opt.value = '600x600';
                    opt.textContent = '600x600';
                    qualitySelect.appendChild(opt);
                }
            }
        })
        .catch(() => {});
}



// 添加表单提交验证
document.addEventListener('DOMContentLoaded', function() {
    restoreHelpSections();

    const uploadForm = document.querySelector('form[enctype="multipart/form-data"]');
    const printButton = document.getElementById('printButton');
    const copiesSelect = document.getElementById('copiesSelect');
    const copiesCustomWrap = document.getElementById('copiesCustomWrap');
    const copiesCustomInput = document.getElementById('copiesCustomInput');

    function syncCopiesField() {
        if (!copiesSelect) return;
        const isCustom = copiesSelect.value === 'custom';
        if (copiesCustomWrap) {
            copiesCustomWrap.style.display = isCustom ? 'block' : 'none';
        }
        if (isCustom && copiesCustomInput && (!copiesCustomInput.value || parseInt(copiesCustomInput.value, 10) < 1)) {
            copiesCustomInput.value = '1';
        }
    }

    if (copiesSelect) {
        copiesSelect.addEventListener('change', syncCopiesField);
        syncCopiesField();
    }
    
    if (uploadForm) {
        uploadForm.addEventListener('submit', function(e) {
            const printerSelect = document.getElementById('printerSelect');
            const selectedPrinter = printerSelect ? printerSelect.value : '';
            const copiesField = document.getElementById('copiesSelect');
            const customCopiesInput = document.getElementById('copiesCustomInput');
            const copiesValue = copiesField ? copiesField.value : '1';

            if (copiesField && copiesValue === 'custom') {
                const customCopies = customCopiesInput ? parseInt(customCopiesInput.value, 10) : NaN;
                if (!customCopies || customCopies < 1) {
                    e.preventDefault();
                    alert('请输入有效的自定义份数，至少为 1');
                    return false;
                }
                copiesField.value = String(customCopies);
            }
            
            // 检查是否选择了有效的打印机
            if (!selectedPrinter || selectedPrinter === '' || selectedPrinter === '未检测到可用打印机') {
                e.preventDefault();
                alert('请先选择一个有效的打印机！\\n\\n如果没有看到打印机，请检查：\\n1. 打印机是否正确连接\\n2. 打印机驱动是否安装\\n3. 打印机是否处于联机状态');
                return false;
            }
            
            // 检查是否选择了文件
            const fileInput = document.querySelector('input[type="file"]');
            if (fileInput && fileInput.files.length === 0) {
                e.preventDefault();
                alert('请选择要打印的文件！\\n\\n您可以：\\n1. 点击拖拽区域选择文件\\n2. 直接拖拽文件到上传区域');
                return false;
            }
            
            // 显示加载状态
            if (printButton) {
                printButton.disabled = true;
                printButton.innerHTML = ' 处理中...';
                
                // 5秒后恢复按钮状态（防止页面未刷新）
                setTimeout(() => {
                    printButton.disabled = false;
                    printButton.innerHTML = '上传并打印';
                }, 5000);
            }
            
            return true;
        });
    }
});

// 刷新打印机列表的函数
function refreshPrinterList() {
    const refreshButton = document.querySelector('button[onclick="refreshPrinterList()"]');
    const printerSelect = document.getElementById('printerSelect');
    
    if (refreshButton) {
        refreshButton.disabled = true;
        refreshButton.innerHTML = ' 刷新中...';
    }
    
    // 发送刷新请求
    fetch('/api/refresh_printers')
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                // 清空当前选项
                printerSelect.innerHTML = '';
                
                if (data.printers && data.printers.length > 0) {
                    // 添加新的打印机选项
                    data.printers.forEach(printer => {
                        const option = document.createElement('option');
                        option.value = printer;
                        option.textContent = printer;
                        
                        // 如果是默认打印机，添加标记并选中
                        if (printer === data.default_printer) {
                            option.textContent += ' (默认)';
                            option.selected = true;
                        }
                        
                        printerSelect.appendChild(option);
                    });
                    
                    // 显示成功消息
                    alert(data.message);

                    // 刷新当前选中打印机的能力（纸张/分辨率）
                    refreshPrinterInfo();
                } else {
                    // 没有找到打印机
                    const option = document.createElement('option');
                    option.value = '';
                    option.textContent = '未检测到可用打印机';
                    printerSelect.appendChild(option);
                    
                    alert('未检测到可用的物理打印机');
                }
            } else {
                alert('刷新失败: ' + data.error);
            }
        })
        .catch(error => {
            console.error('刷新打印机列表失败:', error);
            alert('刷新失败，请检查网络连接');
        })
        .finally(() => {
            // 恢复按钮状态
            if (refreshButton) {
                refreshButton.disabled = false;
                refreshButton.innerHTML = ' 刷新';
            }
        });
}

// ============= 页面切换功能 =============

function switchTab(tabName) {
    // 获取标签页按钮
    const printTabBtn = document.getElementById('printTabBtn');
    const scanTabBtn = document.getElementById('scanTabBtn');
    
    // 获取标签页内容
    const printTab = document.getElementById('printTab');
    const scanTab = document.getElementById('scanTab');
    
    if (tabName === 'print') {
        // 显示打印标签页
        printTab.style.display = 'block';
        scanTab.style.display = 'none';
        
        // 更新按钮样式
        printTabBtn.className = 'btn btn-primary';
        scanTabBtn.className = 'btn btn-outline-primary';
        
        // 更新页面标题
        document.title = '内网打印及扫描服务 - 打印';
        
    } else if (tabName === 'scan') {
        // 显示扫描标签页
        printTab.style.display = 'none';
        scanTab.style.display = 'block';
        
        // 更新按钮样式
        printTabBtn.className = 'btn btn-outline-primary';
        scanTabBtn.className = 'btn btn-primary';
        
        // 更新页面标题
        document.title = '内网打印及扫描服务 - 扫描';
        
        // 如果是第一次切换到扫描标签，刷新扫描仪列表和扫描文件列表
        if (typeof refreshScannerList === 'function') {
            refreshScannerList();
        }
        if (typeof refreshScannedFiles === 'function') {
            refreshScannedFiles();
        }
    }
    
    // 保存当前标签页到localStorage
    try {
        localStorage.setItem('currentTab', tabName);
    } catch (e) {
        // 忽略localStorage错误
    }
}

// 页面加载时恢复上次选择的标签页
function restoreLastTab() {
    try {
        const lastTab = localStorage.getItem('currentTab');
        if (lastTab && (lastTab === 'print' || lastTab === 'scan')) {
            switchTab(lastTab);
        } else {
            // 默认显示打印标签页
            switchTab('print');
        }
    } catch (e) {
        // 如果localStorage不可用，默认显示打印标签页
        switchTab('print');
    }
}

function setHelpSectionState(sectionKey, isExpanded) {
    const section = document.querySelector('[data-collapse-key="' + sectionKey + '"]');
    if (!section) return;

    if (isExpanded) {
        section.classList.remove('collapsed');
    } else {
        section.classList.add('collapsed');
    }

    try {
        localStorage.setItem('helpSectionState:' + sectionKey, isExpanded ? 'expanded' : 'collapsed');
    } catch (e) {
        // 忽略localStorage错误
    }
}

function toggleHelpSection(sectionKey) {
    const section = document.querySelector('[data-collapse-key="' + sectionKey + '"]');
    if (!section) return;
    setHelpSectionState(sectionKey, section.classList.contains('collapsed'));
}

function handleHelpToggleKey(event, sectionKey) {
    if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        toggleHelpSection(sectionKey);
    }
}

function restoreHelpSections() {
    const helpSections = document.querySelectorAll('[data-collapse-key]');
    helpSections.forEach(section => {
        const sectionKey = section.getAttribute('data-collapse-key');
        let isExpanded = true;
        try {
            const savedState = localStorage.getItem('helpSectionState:' + sectionKey);
            if (savedState === 'collapsed') {
                isExpanded = false;
            }
        } catch (e) {
            // 忽略localStorage错误，默认展开
        }
        setHelpSectionState(sectionKey, isExpanded);
    });
}

// ============= 扫描功能JavaScript =============

// 刷新扫描仪列表
function refreshScannerList() {
    const scannerSelect = document.getElementById('scannerSelect');
    const refreshButton = document.querySelector('button[onclick="refreshScannerList()"]');
    const helpText = document.getElementById('scannerHelpText');
    
    if (refreshButton) {
        refreshButton.disabled = true;
        refreshButton.innerHTML = ' 检测中...';
    }
    
    // 显示加载状态
    scannerSelect.innerHTML = '<option value="">正在检测扫描仪...</option>';
    
    fetch('/api/scanners')
        .then(response => response.json())
        .then(data => {
            scannerSelect.innerHTML = '';
            
            if (data.status === 'success' && data.scanners && data.scanners.length > 0) {
                data.scanners.forEach(scanner => {
                    const option = document.createElement('option');
                    option.value = scanner.id;
                    option.textContent = scanner.name;
                    option.setAttribute('data-type', scanner.type);
                    option.setAttribute('data-available', scanner.available);
                    
                    if (!scanner.available) {
                        option.textContent += ' (不可用)';
                        option.disabled = true;
                    }
                    
                    scannerSelect.appendChild(option);
                });
                
                // 自动选择第一个可用的扫描仪
                const firstAvailable = data.scanners.find(s => s.available);
                if (firstAvailable) {
                    scannerSelect.value = firstAvailable.id;
                }
                
                // 检查是否只有默认选项（即未检测到真实扫描仪）
                const realScanners = data.scanners.filter(s => s.type !== 'Default');
                if (realScanners.length > 0) {
                    helpText.innerHTML = `<small> 检测到 ${realScanners.length} 台扫描设备</small>`;
                } else {
                    helpText.innerHTML = '<small>️ 未检测到扫描仪，将尝试使用系统默认设备，可尝试扫描</small>';
                }
                
                // 启用扫描按钮
                const scanButton = document.getElementById('scanButton');
                if (scanButton) {
                    scanButton.disabled = false;
                }
            } else {
                const option = document.createElement('option');
                option.value = 'default';
                option.textContent = '未检测到扫描仪';
                scannerSelect.appendChild(option);
                
                helpText.innerHTML = '<small>️ 未检测到扫描仪，将尝试使用系统默认设备，可尝试扫描</small>';
            }
        })
        .catch(error => {
            console.error('获取扫描仪列表失败:', error);
            scannerSelect.innerHTML = '<option value="default">未检测到扫描仪</option>';
            helpText.innerHTML = '<small> 扫描仪检测失败，将使用默认设备</small>';
        })
        .finally(() => {
            if (refreshButton) {
                refreshButton.disabled = false;
                refreshButton.innerHTML = ' 刷新';
            }
        });
}

// 开始扫描
function startScan() {
    const scannerSelect = document.getElementById('scannerSelect');
    const formatSelect = document.getElementById('formatSelect');
    const scanButton = document.getElementById('scanButton');
    
    if (!scannerSelect.value) {
        alert('请先选择一个扫描仪！');
        return;
    }
    
    // 弹出确认对话框
    const confirmMessage = `️ 扫描确认\n\n请确认以下操作已完成：\n\n 扫描仪中已放入要扫描的文件\n 文件位置和方向正确\n 扫描仪盖子已盖好\n 当前没有打印任务在进行\n\n扫描仪: ${scannerSelect.options[scannerSelect.selectedIndex].text}\n格式: ${formatSelect.value}\n\n️ 扫描期间请勿使用打印功能\n\n确定开始扫描吗？`;
    
    if (confirm(confirmMessage)) {
        // 用户确认后开始扫描
        performScan();
    }
}

// 执行实际的扫描操作
function performScan() {
    const scannerSelect = document.getElementById('scannerSelect');
    const formatSelect = document.getElementById('formatSelect');
    const scanButton = document.getElementById('scanButton');
    
    // 显示扫描进度
    scanButton.disabled = true;
    scanButton.innerHTML = ' 扫描中... 请勿关闭';
    
    // 创建JSON数据
    const requestData = {
        scanner_id: scannerSelect.value,
        scanner_name: scannerSelect.options[scannerSelect.selectedIndex].text,
        format: formatSelect.value
    };
    
    // 发送扫描请求
    fetch('/api/scan', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(requestData)
    })
    .then(response => response.json())
    .then(data => {
        if (data.status === 'success' || data.status === 'warning') {
            showAlert(data.status === 'success' ? 'success' : 'warning', ` ${data.message}`);
            
            // 扫描成功或部分成功后刷新文件列表
            setTimeout(() => {
                if (typeof refreshScannedFiles === 'function') {
                    refreshScannedFiles();
                }
            }, 2000);
        } else {
            showAlert('danger', ` 扫描失败: ${data.error}`);
        }
    })
    .catch(error => {
        console.error('扫描请求失败:', error);
        showAlert('danger', ` 扫描请求失败: ${error.message || error}`);
    })
    .finally(() => {
        // 恢复扫描按钮
        scanButton.disabled = false;
        scanButton.innerHTML = ' 开始扫描';
    });
}

// 显示扫描进行中的遮罩层


// 页面加载完成后的初始化
document.addEventListener('DOMContentLoaded', function() {
    // 恢复上次选择的标签页
    restoreLastTab();
    
    const printerSelect = document.getElementById('printerSelect');
    if (printerSelect && printerSelect.value) {
        refreshPrinterInfo();
        printerSelect.addEventListener('change', refreshPrinterInfo);
    }
    

    
    // 初始化拖拽文件功能
    initFileDragDrop();
    
    // 注意：不在这里初始化扫描功能，而是在切换到扫描标签时才初始化
});

// 拖拽文件功能
function initFileDragDrop() {
    const dropArea = document.getElementById('fileDropArea');
    const fileInput = document.getElementById('fileInput');
    const fileList = document.getElementById('fileList');
    const selectedFiles = document.getElementById('selectedFiles');
    
    if (!dropArea || !fileInput) return;
    
    let currentFiles = [];
    
    // 支持的文件类型
    const allowedTypes = ['pdf', 'jpg', 'jpeg', 'png', 'txt', 'doc', 'docx', 'ppt', 'pptx', 'xls', 'xlsx'];
    
    // 点击区域触发文件选择
    dropArea.addEventListener('click', function(e) {
        // 只阻止链接跳转，不阻止点击事件
        if (e.target.tagName === 'A') {
            e.preventDefault();
        }
        fileInput.click();
    });
    
    // 文件输入框变化
    fileInput.addEventListener('change', function(e) {
        const files = Array.from(e.target.files);
        addFiles(files);
    });
    
    // 阻止默认的拖拽行为
    ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
        dropArea.addEventListener(eventName, preventDefaults, false);
    });
    
    // 只在document上阻止拖拽，不影响点击
    ['dragenter', 'dragover'].forEach(eventName => {
        document.body.addEventListener(eventName, function(e) {
            if (e.target !== dropArea && !dropArea.contains(e.target)) {
                e.preventDefault();
                e.stopPropagation();
            }
        }, false);
    });
    
    // 高亮拖拽区域
    ['dragenter', 'dragover'].forEach(eventName => {
        dropArea.addEventListener(eventName, highlight, false);
    });
    
    ['dragleave', 'drop'].forEach(eventName => {
        dropArea.addEventListener(eventName, unhighlight, false);
    });
    
    // 处理拖拽文件
    dropArea.addEventListener('drop', handleDrop, false);
    
    function preventDefaults(e) {
        e.preventDefault();
        e.stopPropagation();
    }
    
    function highlight() {
        dropArea.classList.add('drag-over');
        dropArea.querySelector('.drop-icon').textContent = '';
    }
    
    function unhighlight() {
        dropArea.classList.remove('drag-over');
        dropArea.querySelector('.drop-icon').textContent = '';
    }
    
    function handleDrop(e) {
        const dt = e.dataTransfer;
        const files = Array.from(dt.files);
        addFiles(files);
    }
    
    function addFiles(newFiles) {
        // 过滤允许的文件类型
        const validFiles = newFiles.filter(file => {
            const extension = file.name.split('.').pop().toLowerCase();
            return allowedTypes.includes(extension);
        });
        
        if (validFiles.length !== newFiles.length) {
            const invalidCount = newFiles.length - validFiles.length;
            alert(`有 ${invalidCount} 个文件格式不支持，已忽略。\\n支持的格式: ${allowedTypes.join(', ')}`);
        }
        
        // 添加有效文件到列表（避免重复）
        validFiles.forEach(file => {
            const exists = currentFiles.some(f => f.name === file.name && f.size === file.size);
            if (!exists) {
                currentFiles.push(file);
            }
        });
        
        updateFileList();
        updateFileInput();
    }
    
    function removeFile(index) {
        currentFiles.splice(index, 1);
        updateFileList();
        updateFileInput();
    }
    
    function updateFileList() {
        if (currentFiles.length === 0) {
            fileList.style.display = 'none';
            return;
        }
        
        fileList.style.display = 'block';
        selectedFiles.innerHTML = '';
        
        currentFiles.forEach((file, index) => {
            const fileItem = document.createElement('div');
            fileItem.className = 'file-item';
            fileItem.innerHTML = `
                <span class="file-name">${file.name}</span>
                <span class="file-size">${formatFileSize(file.size)}</span>
                <div class="file-actions" style="display:inline-block; margin-left:10px;">
                    <button type="button" class="btn btn-sm btn-outline-secondary me-1" onclick="previewLocalFile(${index})" title="预览文件">️ 预览</button>
                    <button type="button" class="remove-btn" onclick="removeFileFromList(${index})" title="移除文件">&times;</button>
                </div>
            `;
            selectedFiles.appendChild(fileItem);
        });
    }
    
    function updateFileInput() {
        // 创建新的文件列表
        const dt = new DataTransfer();
        currentFiles.forEach(file => {
            dt.items.add(file);
        });
        fileInput.files = dt.files;
    }
    
    function formatFileSize(bytes) {
        if (bytes === 0) return '0 B';
        const k = 1024;
        const sizes = ['B', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    }
    
    // 全局函数，供HTML调用
    window.removeFileFromList = function(index) {
        try {
            const file = currentFiles[index];
            if (file) {
                // 如果 file 上有临时预览 URL，则立即撤销并清理定时器
                try {
                    if (file._previewUrl) {
                        try { URL.revokeObjectURL(file._previewUrl); } catch (e) {}
                        file._previewUrl = null;
                    }
                    if (file._revokeTimer) {
                        clearTimeout(file._revokeTimer);
                        file._revokeTimer = null;
                    }
                } catch (e) {
                    // 忽略撤销错误
                }
            }

            currentFiles.splice(index, 1);
            updateFileList();
            updateFileInput();
        } catch (e) {
            console.error('removeFileFromList error:', e);
        }
    };

    // 全局函数：预览本地待上传文件（使用临时 Blob URL）
    window.previewLocalFile = function(index) {
        try {
            const file = currentFiles[index];
            if (!file) return;

            // 创建模态框容器（如果尚未创建）
            let modal = document.getElementById('localPreviewModal');
            if (!modal) {
                modal = document.createElement('div');
                modal.id = 'localPreviewModal';
                modal.className = 'modal fade';
                modal.innerHTML = `
                    <div class="modal-dialog modal-xl modal-dialog-centered">
                        <div class="modal-content">
                            <div class="modal-header">
                                <h5 class="modal-title">文件预览</h5>
                                <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="关闭"></button>
                            </div>
                            <div class="modal-body" style="max-height:80vh; overflow:auto;">
                                <div id="localPreviewContent"></div>
                            </div>
                            <div class="modal-footer">
                                <a id="localPreviewDownload" class="btn btn-sm btn-outline-secondary" href="#" download style="display:none;">⬇️ 下载</a>
                                <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">关闭</button>
                            </div>
                        </div>
                    </div>`;
                document.body.appendChild(modal);

                // 当模态关闭时撤销任何临时 URL（如果 modal 关闭，说明用户结束预览）
                modal.addEventListener('hidden.bs.modal', function() {
                    try {
                        // 撤销所有文件上的 preview URL（保守清理）
                        currentFiles.forEach(f => {
                            try {
                                if (f && f._previewUrl) {
                                    try { URL.revokeObjectURL(f._previewUrl); } catch (e) {}
                                    f._previewUrl = null;
                                }
                                if (f && f._revokeTimer) {
                                    try { clearTimeout(f._revokeTimer); } catch (e) {}
                                    f._revokeTimer = null;
                                }
                            } catch (e) {}
                        });
                    } catch (e) {}
                });
            }

            const content = document.getElementById('localPreviewContent');
            const downloadLink = document.getElementById('localPreviewDownload');
            content.innerHTML = '';
            downloadLink.style.display = 'none';
            downloadLink.href = '#';

            const mime = file.type || '';
            const name = file.name || '文件';

            // 文本类型：使用 FileReader 直接读取并显示（避免使用 objectURL）
            if (mime.startsWith('text/') || /\.(txt|md|csv)$/i.test(name)) {
                const reader = new FileReader();
                reader.onload = function(e) {
                    const pre = document.createElement('pre');
                    pre.style.whiteSpace = 'pre-wrap';
                    pre.style.wordBreak = 'break-word';
                    pre.textContent = e.target.result;
                    content.appendChild(pre);
                };
                reader.onerror = function() {
                    content.innerHTML = '<div class="text-danger">无法读取文本内容</div>';
                };
                reader.readAsText(file, 'utf-8');
            }
            // 图片：使用 objectURL 嵌入 <img>
            else if (mime.startsWith('image/') || /\.(jpg|jpeg|png|gif|bmp|webp)$/i.test(name)) {
                let url = file._previewUrl;
                if (!url) {
                    url = URL.createObjectURL(file);
                    try { file._previewUrl = url; } catch (e) {}
                    try {
                        file._revokeTimer = setTimeout(() => {
                            try { URL.revokeObjectURL(url); } catch (e) {}
                            try { file._previewUrl = null; } catch (e) {}
                            try { file._revokeTimer = null; } catch (e) {}
                        }, 5 * 60 * 1000);
                    } catch (e) {}
                }
                const img = document.createElement('img');
                img.src = url;
                img.className = 'img-fluid';
                img.style.maxHeight = '70vh';
                content.appendChild(img);
                downloadLink.href = url;
                downloadLink.download = name;
                downloadLink.style.display = 'inline-block';
            }
            // PDF：使用 objectURL 嵌入 <iframe>
            else if (mime === 'application/pdf' || /\.pdf$/i.test(name)) {
                let url = file._previewUrl;
                if (!url) {
                    url = URL.createObjectURL(file);
                    try { file._previewUrl = url; } catch (e) {}
                    try {
                        file._revokeTimer = setTimeout(() => {
                            try { URL.revokeObjectURL(url); } catch (e) {}
                            try { file._previewUrl = null; } catch (e) {}
                            try { file._revokeTimer = null; } catch (e) {}
                        }, 5 * 60 * 1000);
                    } catch (e) {}
                }
                const iframe = document.createElement('iframe');
                iframe.src = url;
                iframe.style.width = '100%';
                iframe.style.height = '70vh';
                iframe.frameBorder = '0';
                content.appendChild(iframe);
                downloadLink.href = url;
                downloadLink.download = name;
                downloadLink.style.display = 'inline-block';
            }
            // 其他文件类型：提示并提供下载链接（不自动下载）
            else {
                let url = file._previewUrl;
                if (!url) {
                    url = URL.createObjectURL(file);
                    try { file._previewUrl = url; } catch (e) {}
                    try {
                        file._revokeTimer = setTimeout(() => {
                            try { URL.revokeObjectURL(url); } catch (e) {}
                            try { file._previewUrl = null; } catch (e) {}
                            try { file._revokeTimer = null; } catch (e) {}
                        }, 5 * 60 * 1000);
                    } catch (e) {}
                }
                content.innerHTML = `<div>此文件类型无法在浏览器内预览。您可以点击下方"下载"按钮在本地打开。</div>`;
                downloadLink.href = url;
                downloadLink.download = name;
                downloadLink.style.display = 'inline-block';
            }

            // 显示模态框
            const bsModal = new bootstrap.Modal(modal);
            bsModal.show();

        } catch (e) {
            alert('无法预览该文件: ' + (e && e.message ? e.message : e));
        }
    };

    // 页面卸载时撤销所有尚未撤销的 Blob URL
    window.addEventListener('beforeunload', function() {
        try {
            currentFiles.forEach(file => {
                try {
                    if (file && file._previewUrl) {
                        try { URL.revokeObjectURL(file._previewUrl); } catch (e) {}
                        file._previewUrl = null;
                    }
                    if (file && file._revokeTimer) {
                        try { clearTimeout(file._revokeTimer); } catch (e) {}
                        file._revokeTimer = null;
                    }
                } catch (e) {}
            });
        } catch (e) {}
    });
}

// 删除队列中的文件
function deleteFile(filename) {
    if (confirm(`确定要从队列中删除文件 "${filename}" 吗？\\n\\n删除后无法恢复，如果需要打印需要重新上传。`)) {
        // 显示删除中状态
        const deleteButtons = document.querySelectorAll(`button[onclick="deleteFile('${filename}')"]`);
        deleteButtons.forEach(btn => {
            btn.disabled = true;
            btn.innerHTML = ' 删除中...';
        });
        
        // 发送删除请求
        fetch('/api/delete_file', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                filename: filename
            })
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                // 删除成功，刷新页面或移除表格行
                const row = document.querySelector(`button[onclick="deleteFile('${filename}')"]`).closest('tr');
                if (row) {
                    row.style.backgroundColor = '#f8f9fa';
                    row.style.opacity = '0.5';
                    setTimeout(() => {
                        location.reload(); // 刷新页面以更新队列
                    }, 500);
                }
                
                // 显示成功消息
                showAlert('success', ` 文件 "${filename}" 已从队列中删除`);
            } else {
                showAlert('danger', ` 删除失败: ${data.error}`);
                // 恢复按钮状态
                deleteButtons.forEach(btn => {
                    btn.disabled = false;
                    btn.innerHTML = '️ 删除';
                });
            }
        })
        .catch(error => {
            console.error('删除文件时发生错误:', error);
            showAlert('danger', ` 删除文件时发生网络错误: ${error.message || error}`);
            // 恢复按钮状态
            deleteButtons.forEach(btn => {
                btn.disabled = false;
                btn.innerHTML = '️ 删除';
            });
        });
    }
}

// 显示提示消息
function showAlert(type, message) {
    // 创建提示框
    const alertDiv = document.createElement('div');
    alertDiv.className = `alert alert-${type} alert-dismissible fade show`;
    alertDiv.style.position = 'fixed';
    alertDiv.style.top = '20px';
    alertDiv.style.right = '20px';
    alertDiv.style.zIndex = '9999';
    alertDiv.style.minWidth = '300px';
    alertDiv.innerHTML = `
        ${message}
        <button type="button" class="btn-close" onclick="this.parentElement.remove()" aria-label="Close"></button>
    `;
    
    document.body.appendChild(alertDiv);
    
    // 3秒后自动消失
    setTimeout(() => {
        if (alertDiv.parentElement) {
            alertDiv.remove();
        }
    }, 3000);
}

// 批量删除功能
function deleteAllFiles() {
    const fileRows = document.querySelectorAll('table tbody tr');
    const fileCount = fileRows.length;
    
    // 排除空队列的情况
    const emptyRow = document.querySelector('table tbody tr td[colspan]');
    if (emptyRow) {
        showAlert('info', '队列为空，没有文件需要删除');
        return;
    }
    
    if (confirm(`确定要删除队列中的所有 ${fileCount} 个文件吗？\\n\\n删除后无法恢复！`)) {
        fetch('/api/delete_all_files', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                showAlert('success', ` 已删除 ${data.count} 个文件`);
                setTimeout(() => {
                    location.reload();
                }, 1000);
            } else {
                showAlert('danger', ` 批量删除失败: ${data.error}`);
            }
        })
        .catch(error => {
            console.error('批量删除时发生错误:', error);
            showAlert('danger', ` 批量删除时发生网络错误: ${error.message || error}`);
        });
    }
}

// 清空所有扫描文件
function clearAllScannedFiles() {
    const filesList = document.getElementById('scannedFilesList');
    
    // 检查是否有文件
    if (!filesList.textContent.includes('个扫描文件')) {
        showAlert('info', '暂无扫描文件需要清空');
        return;
    }
    
    // 确认删除
    if (!confirm('确定要清空所有扫描文件吗？此操作不可恢复。')) {
        return;
    }
    
    const clearButton = document.querySelector('button[onclick="clearAllScannedFiles()"]');
    if (clearButton) {
        clearButton.disabled = true;
        clearButton.innerHTML = '清空中...';
    }
    
    fetch('/api/clear_scanned_files', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        }
    })
    .then(response => response.json())
    .then(data => {
        if (data.status === 'success') {
            showAlert('success', `已清空 ${data.deleted_count} 个扫描文件`);
            refreshScannedFiles();
        } else {
            showAlert('danger', `清空失败: ${data.error || data.message}`);
        }
    })
    .catch(error => {
        console.error('清空扫描文件时发生错误:', error);
        showAlert('danger', `网络错误: ${error.message}`);
    })
    .finally(() => {
        if (clearButton) {
            clearButton.disabled = false;
            clearButton.innerHTML = ' 清空队列';
        }
    });
}

// ================== 扫描文件管理功能 ==================

// 刷新扫描文件列表
function refreshScannedFiles() {
    const refreshButton = document.querySelector('button[onclick="refreshScannedFiles()"]');
    const originalText = refreshButton ? refreshButton.innerHTML : '';
    
    if (refreshButton) {
        refreshButton.disabled = true;
        refreshButton.innerHTML = '刷新中...';
    }
    
    fetch('/api/scanned_files')
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                displayScannedFiles(data.files);
            } else {
                console.error('获取扫描文件列表失败:', data.error);
                document.getElementById('scannedFilesList').innerHTML = 
                    `<div class="text-center text-danger py-4">
                        <i class="bi bi-exclamation-circle" style="font-size: 2em;"></i>
                        <p class="mt-2">获取扫描文件失败: ${data.error}</p>
                    </div>`;
            }
        })
        .catch(error => {
            console.error('获取扫描文件列表时发生错误:', error);
            document.getElementById('scannedFilesList').innerHTML = 
                `<div class="text-center text-danger py-4">
                    <i class="bi bi-wifi-off" style="font-size: 2em;"></i>
                    <p class="mt-2">网络错误: ${error.message}</p>
                </div>`;
        })
        .finally(() => {
            if (refreshButton) {
                refreshButton.disabled = false;
                refreshButton.innerHTML = originalText;
            }
        });
}

// 显示扫描文件列表
function displayScannedFiles(files) {
    const filesList = document.getElementById('scannedFilesList');
    
    if (!files || files.length === 0) {
        filesList.innerHTML = 
            `<div class="text-center text-muted py-4">
                <i class="bi bi-folder2-open" style="font-size: 2em;"></i>
                <p class="mt-2">暂无扫描文件</p>
                <small>扫描完成的文件会显示在这里</small>
            </div>`;
        return;
    }
    
    let html = `
        <div class="mb-3">
            <span class="text-muted">共 ${files.length} 个扫描文件</span>
        </div>
        <div class="table-responsive">
            <table class="table table-hover">
                <thead class="table-light">
                    <tr>
                        <th>文件名</th>
                        <th>类型</th>
                        <th>大小</th>
                        <th>创建时间</th>
                        <th>操作</th>
                    </tr>
                </thead>
                <tbody>
    `;
    
    files.forEach(file => {
        const typeIcon = getFileTypeIcon(file.type, file.extension);
        const canPreview = file.type === 'image';
        
        html += `
            <tr>
                <td>
                    ${typeIcon} 
                    ${canPreview ? 
                        `<a href="#" onclick="previewScannedFile('${file.filename}')" class="text-decoration-none">${file.filename}</a>` :
                        file.filename
                    }
                </td>
                <td>
                    <span class="badge bg-secondary">${file.extension.toUpperCase()}</span>
                </td>
                <td class="text-muted">${file.size_str}</td>
                <td class="text-muted">${file.created}</td>
                <td>
                    <div class="btn-group btn-group-sm">
                        ${canPreview ? 
                            `<button class="btn btn-outline-info" onclick="previewScannedFile('${file.filename}')" title="预览">
                                预览
                            </button>` : ''
                        }
                        <button class="btn btn-outline-success" onclick="downloadScannedFile('${file.filename}')" title="下载">
                            下载
                        </button>
                        <button class="btn btn-outline-primary" onclick="printScannedFile('${file.filename}')" title="打印">
                            打印
                        </button>
                        <button class="btn btn-outline-danger" onclick="deleteScannedFile('${file.filename}')" title="删除">
                            删除
                        </button>
                    </div>
                </td>
            </tr>
        `;
    });
    
    html += `
                </tbody>
            </table>
        </div>
    `;
    
    filesList.innerHTML = html;
}

// 获取文件类型图标
function getFileTypeIcon(type, extension) {
    switch (type) {
        case 'image':
            return '️';
        case 'pdf':
            return '';
        default:
            return '';
    }
}

// 预览扫描文件
function previewScannedFile(filename) {
    const modal = document.createElement('div');
    modal.className = 'modal fade';
    modal.innerHTML = `
        <div class="modal-dialog modal-lg">
            <div class="modal-content">
                <div class="modal-header">
                    <h5 class="modal-title"> 扫描文件预览: ${filename}</h5>
                    <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                </div>
                <div class="modal-body text-center">
                    <img src="/api/scanned_files/${filename}/preview" 
                         class="img-fluid" 
                         style="max-height: 70vh;" 
                         onerror="this.src='data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMjAwIiBoZWlnaHQ9IjIwMCIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj48cmVjdCB3aWR0aD0iMTAwJSIgaGVpZ2h0PSIxMDAlIiBmaWxsPSIjZGRkIi8+PHRleHQgeD0iNTAlIiB5PSI1MCUiIGZvbnQtc2l6ZT0iMTIiIHRleHQtYW5jaG9yPSJtaWRkbGUiIGR5PSIuM2VtIj7ml6Dms5XpooTop4g8L3RleHQ+PC9zdmc+'; this.alt='预览失败';"
                         alt="扫描文件预览">
                </div>
                <div class="modal-footer">
                    <button type="button" class="btn btn-success" onclick="downloadScannedFile('${filename}')">
                         下载
                    </button>
                    <button type="button" class="btn btn-primary" onclick="printScannedFile('${filename}')">
                        ️ 打印
                    </button>
                    <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">关闭</button>
                </div>
            </div>
        </div>
    `;
    
    document.body.appendChild(modal);
    const bsModal = new bootstrap.Modal(modal);
    bsModal.show();
    
    // 模态框关闭后移除DOM元素
    modal.addEventListener('hidden.bs.modal', () => {
        document.body.removeChild(modal);
    });
}

// 下载扫描文件
function downloadScannedFile(filename) {
    const link = document.createElement('a');
    link.href = `/api/scanned_files/${filename}`;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    
    showAlert('info', ` 正在下载: ${filename}`);
}

// 打印扫描文件
function printScannedFile(filename) {
    const printerSelect = document.getElementById('printerSelect');
    const copiesInput = document.getElementById('copiesInput');
    
    if (!printerSelect || !printerSelect.value) {
        showAlert('warning', '️ 请先选择打印机');
        return;
    }
    
    const printer = printerSelect.value;
    const copies = copiesInput ? parseInt(copiesInput.value) || 1 : 1;
    
    if (confirm(`确定要打印扫描文件 "${filename}" 吗？\\n\\n打印机: ${printer}\\n份数: ${copies}`)) {
        fetch(`/api/scanned_files/${filename}/print`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                printer: printer,
                copies: copies
            })
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                showAlert('success', ` ${data.message}`);
            } else {
                showAlert('danger', ` 打印失败: ${data.error}`);
            }
        })
        .catch(error => {
            console.error('打印扫描文件时发生错误:', error);
            showAlert('danger', ` 打印时发生网络错误: ${error.message}`);
        });
    }
}

// 删除扫描文件
function deleteScannedFile(filename) {
    if (confirm(`确定要删除扫描文件 "${filename}" 吗？\\n\\n删除后无法恢复！`)) {
        fetch(`/api/scanned_files/${filename}/delete`, {
            method: 'DELETE'
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                showAlert('success', ` ${data.message}`);
                // 刷新扫描文件列表
                refreshScannedFiles();
            } else {
                showAlert('danger', ` 删除失败: ${data.error}`);
            }
        })
        .catch(error => {
            console.error('删除扫描文件时发生错误:', error);
            showAlert('danger', ` 删除时发生网络错误: ${error.message}`);
        });
    }
}
