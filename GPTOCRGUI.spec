import platform

block_cipher = None

icon_file = 'ocrgui.ico' # 默认 Windows 图标
if platform.system() == "Darwin": # 如果是 macOS
    icon_file = 'ocrgui.icns' # 设置 macOS 图标 

a = Analysis(
    ['GPTOCRGUI.py'], 
    binaries=[],
    datas=[
        ('ocrgui.ico', '.'),
        ('ocrgui.icns', '.'),
        ('utils/*.py', 'utils'),
        ('processors/*.py', 'processors'),
    ],
    hiddenimports=[
        'PIL',
        'openai',
        'pystray',
        'httpx',
        'plyer',
        'plyer.platforms.win.notification',
        'plyer.platforms.macosx.notification',
        'utils.path_tools',
        'utils.config_manager',
        'utils.notification_manager',
        'processors.image_encoder',
        'processors.markdown_processor',
        'keyboard'
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'numpy',
        'pandas',
        'scipy',
        'matplotlib',
        'numba',
        'llvmlite',
        'pyarrow',
        'sqlalchemy',
        'lxml',
        'pygments',
        'pytest',
        'unittest',
        'doctest',
        'tkinter.test',
        'lib2to3',
        'test',
        'tests',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False  # 修改为False
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    name='PillOCR',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon_file if platform.system() == "Windows" else None
)

if platform.system() == "Darwin":
    app = BUNDLE(
        exe,
        name='PillOCR.app',
        icon=icon_file,
        bundle_identifier='com.pebblestudio.pillocr',
        info_plist={
            'LSUIElement': 'YES',
            'CFBundleShortVersionString': '0.0.1',
            'CFBundleName': 'PillOCR',
            'CFBundleDisplayName': 'PillOCR',
            'NSHighResolutionCapable': True,
        }
    )