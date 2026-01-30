import os
import re
import pystray
import pyperclip
import platform
import hashlib

# import keyboard
import threading
import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageGrab, ImageDraw, ImageTk
import time
from openai import OpenAI
import httpx
from utils.path_tools import get_absolute_path
from processors.image_encoder import ImageEncoder
from processors.markdown_processor import MarkdownProcessor
from utils.config_manager import ConfigManager
from utils.hotkey_manager import create_hotkey_manager, HotkeyManager
from utils.notification_manager import NotificationManager


def parse_api_url(url: str) -> tuple:
    """
    解析 API URL，判断是完整 API 地址还是 base_url

    Args:
        url: 用户输入的 URL

    Returns:
        tuple: (base_url, is_full_api_url)
        - 如果是完整 API URL (如 .../chat/completions)，返回 (处理后的base_url, True)
        - 如果是 base_url，返回 (原URL, False)
    """
    url = url.strip().rstrip("/")

    # 检查是否是完整的 API 端点 URL
    api_endpoints = [
        "/chat/completions",
        "/completions",
        "/embeddings",
        "/images/generations",
        "/audio/transcriptions",
        "/audio/translations",
    ]

    for endpoint in api_endpoints:
        if url.endswith(endpoint):
            # 移除端点部分，保留 base_url
            base_url = url[: -len(endpoint)]
            return base_url.rstrip("/"), True

    return url, False


class ImageToMarkdown:
    def __init__(self, log_callback, app):
        self.log_callback = log_callback
        self.app = app
        self.running = False
        self.client = None
        self.gpt_model = "gpt-4o"
        self.image_encoder = ImageEncoder()
        self.markdown_processor = MarkdownProcessor()
        self.current_provider = "OPENAI"
        self.screenshot_hotkey_isNull = True  # 用于标记是否注册了截图快捷键
        self.screenshot_hotkey_triggered = False  # 用于标记是否触发了截图快捷键
        self.process_pre_exist_image = (
            True  # 用于标记是否处理软件启动时已经存在的剪贴板图片
        )
        try:
            self.initial_image = ImageGrab.grabclipboard()
        except Exception:
            self.initial_image = None
        self.system_prompt = (
            "You are a helpful assistant that converts images to markdown format. "
            "If the image contains mathematical formulas, use LaTeX syntax for them. "
            "Return only the markdown content of the image, without any additional words or explanations."
        )
        self.user_prompt = "Here is my image."
        self.max_tokens = 1000
        self.timeout = 60

    def set_prompts(self, system_prompt, user_prompt):
        self.system_prompt = system_prompt
        self.user_prompt = user_prompt

    def set_max_tokens(self, max_tokens):
        self.max_tokens = max_tokens

    def set_timeout(self, timeout):
        self.timeout = timeout

    def set_provider(self, provider):
        """设置当前服务商"""
        self.current_provider = provider

    def set_api_key(self, api_key):
        if not api_key:
            self.log_callback("API Key不能为空")
        os.environ["OPENAI_API_KEY"] = api_key

    def set_proxy(self, proxy):
        """根据服务商设置代理和client"""
        try:
            if self.current_provider == "OPENAI":
                if proxy:
                    self.client = OpenAI(
                        http_client=httpx.Client(
                            transport=httpx.HTTPTransport(proxy=proxy)
                        )
                    )
                else:
                    self.client = OpenAI()
            elif self.current_provider == "火山引擎":
                if proxy:
                    self.client = OpenAI(
                        base_url="https://ark.cn-beijing.volces.com/api/v3",
                        http_client=httpx.Client(
                            transport=httpx.HTTPTransport(proxy=proxy)
                        ),
                    )
                else:
                    self.client = OpenAI(
                        base_url="https://ark.cn-beijing.volces.com/api/v3"
                    )
            elif self.current_provider == "自定义":
                # 从app获取用户设置的URL
                custom_url = self.app.url_var.get().strip()
                if not custom_url:
                    self.log_callback("自定义URL不能为空")
                    return

                # 解析 URL，支持完整 API 地址和 base_url
                base_url, is_full_api = parse_api_url(custom_url)
                if is_full_api:
                    self.log_callback(
                        f"检测到完整API地址，已自动提取base_url: {base_url}"
                    )

                if proxy:
                    self.client = OpenAI(
                        base_url=base_url,
                        http_client=httpx.Client(
                            transport=httpx.HTTPTransport(proxy=proxy)
                        ),
                    )
                else:
                    self.client = OpenAI(base_url=base_url)
        except Exception as e:
            if self.log_callback:
                self.log_callback(f"设置客户端时出错: {str(e)}")

    def set_gpt_model(self, model_name):
        if not model_name:
            self.log_callback("模型不能为空")
            return
        self.gpt_model = model_name

    def process_image(self, image):
        if not self.client:
            raise Exception("请先设置 API Key 或推理接入点")

        base64_img = f"data:image/png;base64,{self.image_encoder.encode_image(image)}"

        response = self.client.chat.completions.create(
            model=self.gpt_model,
            messages=[
                {"role": "system", "content": self.system_prompt},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": self.user_prompt},
                        {"type": "image_url", "image_url": {"url": f"{base64_img}"}},
                    ],
                },
            ],
            max_tokens=self.max_tokens,
            timeout=self.timeout,
        )
        # debug用
        # print(response)
        markdown_content = response.choices[0].message.content
        markdown_content = re.sub(
            r"^```markdown\s*\n(.*?)\n```\s*$", r"\1", markdown_content, flags=re.DOTALL
        )
        return self.markdown_processor.modify_wrappers(markdown_content)

    def process_clipboard_image(self):
        if not self.process_pre_exist_image:
            # 获取当前剪贴板图片的哈希
            try:
                initial_img = ImageGrab.grabclipboard()
                last_hash = self.get_image_hash(initial_img)
            except Exception:
                last_hash = None
        else:
            last_hash = None

        while self.running:
            try:
                if self.screenshot_hotkey_isNull or self.screenshot_hotkey_triggered:
                    image = ImageGrab.grabclipboard()
                    if isinstance(image, Image.Image):
                        current_hash = self.get_image_hash(image)
                        if current_hash != last_hash:
                            self.log_callback("检测到新的剪贴板图像。")
                            self.app.update_icon_status("processing")

                            markdown_content = self.process_image(image)
                            pyperclip.copy(markdown_content)
                            self.log_callback("识别后的内容已复制到剪贴板。")

                            self.app.update_icon_status("success")
                            self.app.send_notification(
                                "success", "识别完成，已复制到剪贴板"
                            )
                            last_hash = current_hash
                            self.screenshot_hotkey_triggered = False
                        elif self.screenshot_hotkey_triggered:
                            # 如果是手动触发快捷键，即使图片没变也给个提示，或者强制重新处理
                            self.log_callback("图片未变化，跳过识别。")
                            self.screenshot_hotkey_triggered = False
            except Exception as e:
                error_msg = str(e)
                self.log_callback(f"发生错误: {error_msg}")
                self.app.update_icon_status("error")
                self.app.send_notification("error", f"识别失败: {error_msg[:50]}")
                # 出错后，将当前哈希记录下来，避免在死循环中重复尝试同一张会导致报错的图片
                try:
                    err_img = ImageGrab.grabclipboard()
                    last_hash = self.get_image_hash(err_img)
                except Exception:
                    pass
                self.screenshot_hotkey_triggered = False
            time.sleep(1)

    def start(self):
        self.running = True
        threading.Thread(target=self.process_clipboard_image, daemon=True).start()

    def stop(self):
        self.running = False

    def set_wrappers(self, inline_wrapper: str, block_wrapper: str):
        """代理到 markdown_processor 的 set_wrappers 方法"""
        self.markdown_processor.set_wrappers(inline_wrapper, block_wrapper)

    def get_image_hash(self, image):
        """计算图片的简单哈希值，用于对比图片是否变化"""
        if image is None:
            return None
        # 缩放到小尺寸并转换为灰度图以提高对比速度
        small_img = image.resize((32, 32), Image.Resampling.LANCZOS).convert("L")
        pixels = list(small_img.getdata())
        avg = sum(pixels) / len(pixels)
        bits = "".join(["1" if p > avg else "0" for p in pixels])
        return hashlib.md5(bits.encode()).hexdigest()


class App:
    def __init__(self, root, processor):
        self.processor = processor
        self.processor.app = self
        self.processor.log_callback = self.log
        self.config_manager = ConfigManager()
        self.notification_manager = NotificationManager()
        self.hotkey_manager = create_hotkey_manager(self.toggle_processing)
        self.hotkey_var = tk.StringVar(value="ctrl+shift+o")
        self.screenshot_hotkey_var = tk.StringVar(value="")  # 添加截图快捷键变量
        self.provider_var = tk.StringVar(
            value="OPENAI"
        )  # 确保 provider_var 在 load_settings 之前定义
        self.url_var = tk.StringVar(value="")
        self.system_prompt_var = tk.StringVar(value=self.processor.system_prompt)
        self.user_prompt_var = tk.StringVar(value=self.processor.user_prompt)
        self.max_tokens_var = tk.IntVar(value=self.processor.max_tokens)
        self.timeout_var = tk.IntVar(value=self.processor.timeout)
        self.process_pre_exist_image_var = tk.BooleanVar(
            value=False
        )  # 用于标记是否处理软件启动时已经存在的剪贴板图片
        self.notification_enabled_var = tk.BooleanVar(value=True)  # 系统通知开关
        self.log_text = tk.Text()  # 确保 log_text 在 load_settings 之前定义
        self.root = root
        self.root.title("OCR")
        self.root.configure(bg="#ffffff")

        # 配置 ttk 样式
        style = ttk.Style()
        style.theme_use("clam")

        # 设置风格
        primary_color = "#95ec69"  # 绿色，与成功状态的胶囊图标一致
        text_color = "#000000"  # 黑色文字
        bg_color = "#ffffff"  # 白色背景

        style.configure(
            "TButton",
            padding=6,
            relief="flat",
            background=primary_color,
            foreground=text_color,
        )
        style.map(
            "TButton",
            background=[("active", primary_color)],
            foreground=[("active", text_color)],
        )
        style.configure("TLabel", background=bg_color, foreground=text_color)
        style.configure("TFrame", background=bg_color)
        style.configure("TLabelframe", background=bg_color)
        # 根据操作系统调整 LabelFrame 标题字体大小
        if platform.system() == "Darwin":
            lf_label_font = ("Segoe UI", 11, "bold")
        else:
            lf_label_font = ("Segoe UI", 9, "bold")
        style.configure(
            "TLabelframe.Label",
            background=bg_color,
            foreground=text_color,
            font=lf_label_font,
        )
        style.configure("TEntry", padding=6)
        style.configure("TCombobox", padding=6)

        # 初始化变量
        self.provider_var = tk.StringVar(value="OPENAI")
        self.api_key_var = tk.StringVar()
        self.proxy_var = tk.StringVar()
        self.model_var = tk.StringVar(value="gpt-4o")
        self.inline_var = tk.StringVar(value="$ $")
        self.block_var = tk.StringVar(value="$$ $$")

        # 定义服务商配置字典
        self.provider_settings = {
            "OPENAI": {"api_key": "", "proxy": "", "model": "gpt-4o"},
            "火山引擎": {"api_key": "", "proxy": "", "model": ""},
            "自定义": {"url": "", "api_key": "", "proxy": "", "model": ""},
        }

        # 主容器，采用两栏布局
        main_frame = ttk.Frame(root, padding=20, style="TFrame")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # 左侧导航
        nav_frame = ttk.Frame(main_frame, style="TFrame")
        nav_frame.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))
        categories = ["模型设置", "LaTeX设置", "其他设置", "日志"]
        if HotkeyManager.should_show_ui():
            categories.append("快捷键设置")
        for cat in categories:
            btn = ttk.Button(
                nav_frame, text=cat, command=lambda c=cat: self.show_section(c)
            )
            btn.pack(fill=tk.X, pady=5)

        # 在导航栏和内容区之间添加灰色竖线分隔
        separator = tk.Frame(main_frame, width=1.5, bg="#CCCCCC")
        separator.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))

        # 右侧内容区
        self.content_frame = ttk.Frame(main_frame, style="TFrame")
        self.content_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # 各分类的 Frame 容器
        self.sections = {}

        # ——— 模型设置 区块 ———
        model_section = ttk.Frame(self.content_frame, style="TFrame")
        self.provider_frame = ttk.LabelFrame(
            model_section, text="服务商选择", padding=10, style="TLabelframe"
        )
        self.provider_frame.pack(fill=tk.X, pady=(0, 10))
        # 添加服务商映射
        self.PROVIDER_MAPPING = {
            "OPENAI": "OPENAI",
            "火山引擎": "火山引擎",
            "自定义": "自定义",
        }
        # 反向映射用于保存
        self.PROVIDER_REVERSE_MAPPING = {v: k for k, v in self.PROVIDER_MAPPING.items()}
        self.provider_dropdown = ttk.Combobox(
            self.provider_frame,
            textvariable=self.provider_var,
            values=list(self.PROVIDER_MAPPING.values()),
            state="readonly",
        )
        self.provider_dropdown.pack(fill=tk.X)
        self.provider_dropdown.bind("<<ComboboxSelected>>", self.on_provider_change)

        # 自定义 URL 配置，先隐藏，只有选择自定义才显示
        self.custom_url_frame = ttk.LabelFrame(
            model_section, text="API 地址", padding=10, style="TLabelframe"
        )
        url_input_frame = ttk.Frame(self.custom_url_frame, style="TFrame")
        url_input_frame.pack(fill=tk.X)
        self.url_entry = ttk.Entry(url_input_frame, textvariable=self.url_var)
        self.url_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
        ttk.Button(url_input_frame, text="保存", command=self.save_custom_url).pack(
            side=tk.RIGHT
        )
        ttk.Label(
            self.custom_url_frame,
            text="支持完整地址 (.../v1/chat/completions) 或 Base URL (.../v1)",
            font=("Segoe UI", 8),
            foreground="#666666",
        ).pack(anchor="w", pady=(5, 0))

        # API Key 设置
        api_frame = ttk.LabelFrame(
            model_section, text="API Key", padding=10, style="TLabelframe"
        )
        api_frame.pack(fill=tk.X, pady=(0, 10))

        self.api_key_entry = ttk.Entry(
            api_frame, textvariable=self.api_key_var, show="•"
        )
        self.api_key_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))

        self.save_api_button = ttk.Button(
            api_frame, text="保存", command=self.save_api_key
        )
        self.save_api_button.pack(side=tk.RIGHT)

        # 模型选择
        self.model_frame = ttk.LabelFrame(
            model_section,
            text="模型选择（请确保模型具有视觉功能）",
            padding=10,
            style="TLabelframe",
        )
        self.model_dropdown = ttk.Combobox(
            self.model_frame, textvariable=self.model_var, state="readonly"
        )
        ttk.Button(self.model_frame, text="保存", command=self.save_model_choice).pack(
            side=tk.RIGHT
        )
        self.model_dropdown.pack(fill=tk.X)
        self.model_dropdown.bind("<<ComboboxSelected>>", self.save_model_choice)

        # 模型输入框
        self.model_entry_frame = ttk.LabelFrame(
            model_section,
            text="模型（请确保模型具有视觉功能）",
            padding=10,
            style="TLabelframe",
        )
        self.model_entry = ttk.Entry(
            self.model_entry_frame, textvariable=self.model_var
        )
        self.model_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
        ttk.Button(
            self.model_entry_frame, text="保存", command=self.save_model_choice
        ).pack(side=tk.RIGHT)

        # 推理接入点框架
        self.endpoint_frame = ttk.LabelFrame(
            model_section,
            text="推理接入点（请确保模型具有视觉功能）",
            padding=10,
            style="TLabelframe",
        )
        self.endpoint_entry = ttk.Entry(
            self.endpoint_frame, textvariable=self.model_var
        )
        self.endpoint_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
        ttk.Button(
            self.endpoint_frame, text="保存", command=self.save_model_choice
        ).pack(side=tk.RIGHT)

        # 代理设置
        proxy_frame = ttk.LabelFrame(
            model_section, text="代理设置", padding=10, style="TLabelframe"
        )
        proxy_frame.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(proxy_frame, text="HTTP代理:").pack(side=tk.LEFT)
        self.proxy_entry = ttk.Entry(proxy_frame, textvariable=self.proxy_var)
        self.proxy_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=10)
        ttk.Button(proxy_frame, text="保存", command=self.save_proxy).pack(
            side=tk.RIGHT
        )

        prompt_frame = ttk.LabelFrame(
            model_section, text="Prompt & Token 设置", padding=10, style="TLabelframe"
        )
        prompt_frame.pack(fill=tk.X, pady=(0, 10))

        # system prompt：多行 Text，自动换行
        system_frame = ttk.Frame(prompt_frame, style="TFrame")
        ttk.Label(system_frame, text="System Prompt:").pack(side=tk.TOP, anchor="w")
        self.system_text = tk.Text(
            system_frame,
            wrap="word",
            height=4,
            bd=0,  # 取消默认边框
            relief="flat",
            bg=bg_color,
            fg=text_color,
            highlightthickness=1.5,  # 边框宽度
            highlightbackground="#b3b0a9",  # 未聚焦时的灰色边框
            highlightcolor="#587d9d",  # 聚焦时的蓝色边框
        )
        self.system_text.insert("1.0", self.system_prompt_var.get())
        self.system_text.pack(fill=tk.X, expand=True, pady=(2, 5))
        system_frame.pack(fill=tk.X, pady=(0, 5))

        # user prompt：多行 Text，自动换行
        user_frame = ttk.Frame(prompt_frame, style="TFrame")
        ttk.Label(user_frame, text="User Prompt:").pack(side=tk.TOP, anchor="w")
        self.user_text = tk.Text(
            user_frame,
            wrap="word",
            height=4,
            bd=0,  # 取消默认边框
            relief="flat",
            bg=bg_color,
            fg=text_color,
            highlightthickness=1.5,  # 边框宽度
            highlightbackground="#b3b0a9",  # 未聚焦时的灰色边框
            highlightcolor="#587d9d",  # 聚焦时的蓝色边框
        )
        self.user_text.insert("1.0", self.user_prompt_var.get())
        self.user_text.pack(fill=tk.X, expand=True, pady=(2, 5))
        user_frame.pack(fill=tk.X, pady=(0, 5))

        # max_tokens
        max_frame = ttk.Frame(prompt_frame, style="TFrame")
        ttk.Label(max_frame, text="Max Tokens:").pack(side=tk.LEFT)
        ttk.Entry(max_frame, textvariable=self.max_tokens_var, width=8).pack(
            side=tk.LEFT, padx=(10, 0)
        )
        ttk.Label(max_frame, text="超时(秒):").pack(side=tk.LEFT, padx=(20, 0))
        ttk.Entry(max_frame, textvariable=self.timeout_var, width=8).pack(
            side=tk.LEFT, padx=(10, 0)
        )
        max_frame.pack(fill=tk.X)

        ttk.Button(prompt_frame, text="保存", command=self.save_settings).pack(
            side=tk.RIGHT
        )

        self.sections["模型设置"] = model_section

        # # ——— 代理设置 区块 ———
        # proxy_section = ttk.Frame(self.content_frame, style='TFrame')
        # # 代理设置
        # proxy_frame = ttk.LabelFrame(proxy_section, text="代理设置", padding=10, style='TLabelframe')
        # proxy_frame.pack(fill=tk.X, pady=(0, 10))

        # ttk.Label(proxy_frame, text="HTTP代理:").pack(side=tk.LEFT)
        # self.proxy_entry = ttk.Entry(proxy_frame, textvariable=self.proxy_var)
        # self.proxy_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=10)
        # ttk.Button(proxy_frame, text="保存", command=self.save_proxy).pack(side=tk.RIGHT)

        # self.sections['代理设置'] = proxy_section

        # ——— LaTeX 设置 区块 ———
        latex_section = ttk.Frame(self.content_frame, style="TFrame")
        # LaTeX 设置
        latex_frame = ttk.LabelFrame(
            latex_section, text="LaTeX 设置", padding=10, style="TLabelframe"
        )
        latex_frame.pack(fill=tk.X, pady=(0, 10))

        inline_frame = ttk.Frame(latex_frame, style="TFrame")
        inline_frame.pack(fill=tk.X, pady=(0, 5))
        ttk.Label(inline_frame, text="行内公式包装符:").pack(side=tk.LEFT)
        inline_combo = ttk.Combobox(
            inline_frame, textvariable=self.inline_var, values=["$ $", "\\( \\)"]
        )
        inline_combo.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(10, 0))

        block_frame = ttk.Frame(latex_frame, style="TFrame")
        block_frame.pack(fill=tk.X)
        ttk.Label(block_frame, text="行间公式包装符:").pack(side=tk.LEFT)
        block_combo = ttk.Combobox(
            block_frame, textvariable=self.block_var, values=["$$ $$", "\\[ \\]"]
        )
        block_combo.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(10, 0))

        self.sections["LaTeX设置"] = latex_section

        # ——— 快捷键设置 区块 ———
        hotkey_section = ttk.Frame(self.content_frame, style="TFrame")
        if HotkeyManager.should_show_ui():
            hotkey_frame = ttk.LabelFrame(
                hotkey_section, text="快捷键设置", padding=10, style="TLabelframe"
            )
            hotkey_frame.pack(fill=tk.X, pady=(0, 10))

            # 启动/停止快捷键（三个单键输入框 + “+” 分隔）
            hk_start_frame = ttk.Frame(hotkey_frame, style="TFrame")
            hk_start_frame.pack(fill=tk.X, pady=(0, 5))
            # 统一第一列宽度，确保对齐
            hk_start_frame.grid_columnconfigure(0, minsize=140)
            ttk.Label(hk_start_frame, text="启动/停止快捷键:").grid(
                row=0, column=0, padx=(0, 5)
            )
            self.hk1 = ttk.Entry(hk_start_frame, width=5)
            self.hk2 = ttk.Entry(hk_start_frame, width=5)
            self.hk3 = ttk.Entry(hk_start_frame, width=5)
            self.hk1.grid(row=0, column=1)
            ttk.Label(hk_start_frame, text="+").grid(row=0, column=2, padx=2)
            self.hk2.grid(row=0, column=3)
            ttk.Label(hk_start_frame, text="+").grid(row=0, column=4, padx=2)
            self.hk3.grid(row=0, column=5)
            ttk.Button(hk_start_frame, text="保存", command=self.save_hotkey).grid(
                row=0, column=6, padx=(10, 0)
            )
            for e in (self.hk1, self.hk2, self.hk3):
                e.bind("<FocusIn>", lambda ev: ev.widget.delete(0, tk.END))
                e.bind("<Key>", self.capture_hotkey)
                e.bind("<FocusOut>", self.save_hotkey)

            # 截图监听快捷键（三个单键输入框 + “+” 分隔）
            hk_snap_frame = ttk.Frame(hotkey_frame, style="TFrame")
            hk_snap_frame.pack(fill=tk.X, pady=(5, 0))
            # 统一第一列宽度，确保对齐
            hk_snap_frame.grid_columnconfigure(0, minsize=140)
            ttk.Label(hk_snap_frame, text="绑定截图快捷键:").grid(
                row=0, column=0, padx=(0, 5)
            )
            self.sk1 = ttk.Entry(hk_snap_frame, width=5)
            self.sk2 = ttk.Entry(hk_snap_frame, width=5)
            self.sk3 = ttk.Entry(hk_snap_frame, width=5)
            self.sk1.grid(row=0, column=1)
            ttk.Label(hk_snap_frame, text="+").grid(row=0, column=2, padx=2)
            self.sk2.grid(row=0, column=3)
            ttk.Label(hk_snap_frame, text="+").grid(row=0, column=4, padx=2)
            self.sk3.grid(row=0, column=5)
            ttk.Button(
                hk_snap_frame, text="保存", command=self.save_screenshot_hotkey
            ).grid(row=0, column=6, padx=(10, 0))
            for e in (self.sk1, self.sk2, self.sk3):
                e.bind("<FocusIn>", lambda ev: ev.widget.delete(0, tk.END))
                e.bind("<Key>", self.capture_hotkey)
                e.bind("<FocusOut>", self.save_screenshot_hotkey)

        self.sections["快捷键设置"] = hotkey_section

        # ——— 其他设置 区块 ———
        others_section = ttk.Frame(self.content_frame, style="TFrame")
        # 启动设置
        startup_frame = ttk.LabelFrame(
            others_section, text="启动设置", padding=10, style="TLabelframe"
        )
        startup_frame.pack(fill=tk.X, pady=(0, 10))
        process_pre_exist_image_check = tk.Checkbutton(
            startup_frame,
            text="处理软件启动时已经存在的剪贴板图片",
            variable=self.process_pre_exist_image_var,
            command=self.save_settings,
            bg=bg_color,
            fg=text_color,
        )
        process_pre_exist_image_check.pack(anchor="w")

        # 通知设置
        notification_frame = ttk.LabelFrame(
            others_section, text="通知设置", padding=10, style="TLabelframe"
        )
        notification_frame.pack(fill=tk.X, pady=(0, 10))
        notification_check = tk.Checkbutton(
            notification_frame,
            text="启用系统通知（识别成功/失败时弹出通知）",
            variable=self.notification_enabled_var,
            command=self.save_settings,
            bg=bg_color,
            fg=text_color,
        )
        notification_check.pack(anchor="w")
        if not NotificationManager.is_available():
            notification_check.config(state="disabled")
            ttk.Label(
                notification_frame, text="（需要安装 plyer 库：pip install plyer）"
            ).pack(anchor="w")

        self.sections["其他设置"] = others_section

        # ——— 日志 区块 ———
        log_section = ttk.Frame(self.content_frame, style="TFrame")
        # 日志显示
        log_frame = ttk.LabelFrame(
            log_section, text="日志", padding=10, style="TLabelframe"
        )
        log_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        self.log_text = tk.Text(
            log_frame,
            height=6,
            font=("Consolas", 9),
            bg="#eeeae7",  # 浅灰色背景
            fg=text_color,
            relief="flat",
            highlightthickness=1.5,
            highlightbackground="#b3b0a9",
            highlightcolor="#587d9d",
            padx=5,
            pady=5,
        )
        self.log_text.pack(fill=tk.BOTH, expand=True)
        self.sections["日志"] = log_section

        # 默认显示
        self.show_section("日志")

        # 设置窗口图标
        icon_path = get_absolute_path("ocrgui.ico")
        icon_image = Image.open(icon_path)
        self.icon_photo = ImageTk.PhotoImage(icon_image)
        self.root.iconphoto(False, self.icon_photo)

        self.root.protocol("WM_DELETE_WINDOW", self.hide_window)

        # 初始化其他组件
        self.icon = None
        self.icon_image = None
        self.running_state = False
        self.create_tray_icon()

        # 加载设置
        self.load_settings()

        # 绑定包装符变化
        # 添加防抖计时器
        self.debounce_timer = None
        self.last_wrapper_change = time.time()

        self.inline_var.trace_add("write", self.debounced_update_wrappers)
        self.block_var.trace_add("write", self.debounced_update_wrappers)

        self.processor.set_gpt_model(
            self.model_var.get()
        )  # 确保在加载配置后更新模型设置

        # 自动开始处理
        self.root.after(1000, self.auto_start)
        # self.update_client_settings()
        # 初始隐藏推理接入点
        if self.provider_var.get() == "OPENAI":
            self.model_frame.pack_forget()
            self.model_frame.pack(after=self.provider_frame, fill=tk.X, pady=(0, 10))
        elif self.provider_var.get() == "火山引擎":
            self.model_frame.pack_forget()
            self.endpoint_frame.pack(after=self.provider_frame, fill=tk.X, pady=(0, 10))
        elif self.provider_var.get() == "自定义":
            self.model_frame.pack_forget()

    def show_section(self, name):
        """在内容区切换到指定分类的 Frame"""
        for sec in self.sections.values():
            sec.pack_forget()
        self.sections[name].pack(fill=tk.BOTH, expand=True)
        self.root.update_idletasks()

    def debounced_update_wrappers(self, *args):
        """防抖包装符更新"""
        DEBOUNCE_TIME = 2.0  # 1秒防抖时间

        # 取消之前的定时器
        if self.debounce_timer:
            self.debounce_timer.cancel()

        # 创建新定时器
        self.debounce_timer = threading.Timer(DEBOUNCE_TIME, self.update_wrappers)
        self.debounce_timer.start()

    def auto_start(self):
        self.start_processing()
        self.running_state = True
        self.icon.menu = self.create_menu()

    # def auto_start(self):
    #     if self.auto_start_var.get():  # 只有当用户启用自动启动时才开始处理
    #         self.start_processing()
    #         self.running_state = True
    #         self.icon.menu = self.create_menu()
    #     else:
    #         self.log("自动启动已禁用，请手动启动处理")

    def log(self, message):
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)

    def update_wrappers(self):
        """更新包装符并保存配置"""
        inline_wrapper = self.inline_var.get()
        block_wrapper = self.block_var.get()
        self.processor.set_wrappers(inline_wrapper, block_wrapper)
        self.save_settings()  # 自动保存配置
        self.log("已更新并保存LaTeX包装符设置")

    def save_hotkey(self):
        """保存快捷键设置"""
        if not HotkeyManager.is_supported():
            return

        try:
            # 从三个输入框拼接
            parts = [
                self.hk1.get().strip(),
                self.hk2.get().strip(),
                self.hk3.get().strip(),
            ]
            combo = "+".join(p.lower() for p in parts if p)
            self.hotkey_var.set(combo)

            self.unregister_hotkey()
            self.register_hotkey()
            self.save_settings()
            self.log(f"启动/停止快捷键已设置为: {combo}")
        except Exception as e:
            self.log(f"快捷键设置失败: {e}")

    def register_hotkey(self):
        """注册全局热键"""
        if not HotkeyManager.is_supported():
            return  # 在不支持的平台上什么也不做

        try:
            result = self.hotkey_manager.register_hotkey(self.hotkey_var.get())
            if result:
                # 分割快捷键字符串并填充到输入框
                parts = self.hotkey_var.get().strip().split("+")
                for i in range(1, 4):
                    entry = getattr(self, f"hk{i}")
                    entry.delete(0, tk.END)
                    if i <= len(parts) and parts[i - 1]:
                        entry.insert(0, parts[i - 1].lower())

                self.log(f"已注册快捷键: {self.hotkey_var.get()}")
            else:
                self.log("注册快捷键失败")
        except Exception as e:
            self.log(f"注册快捷键失败: {e}")

    def unregister_hotkey(self):
        if not HotkeyManager.is_supported():
            return

        try:
            self.hotkey_manager.unregister_hotkey()
        except Exception:
            pass

    def capture_hotkey(self, event):
        """实时捕获按键组合"""
        key = event.keysym.lower()
        # 归一化左右修饰键
        mod_map = {
            "shift_l": "shift",
            "shift_r": "shift",
            "control_l": "ctrl",
            "control_r": "ctrl",
            "alt_l": "alt",
            "alt_r": "alt",
        }
        key = mod_map.get(key, key)
        event.widget.delete(0, tk.END)
        event.widget.insert(0, key)
        return "break"

    def save_screenshot_hotkey(self, event=None):
        """保存截图快捷键设置"""
        if not HotkeyManager.is_supported():
            return

        try:
            parts = [
                self.sk1.get().strip(),
                self.sk2.get().strip(),
                self.sk3.get().strip(),
            ]
            combo = "+".join(p.lower() for p in parts if p)
            self.screenshot_hotkey_var.set(combo)
            self.unregister_screenshot_listener()
            self.register_screenshot_listener()
            self.save_settings()
            self.log(f"截图监听快捷键已设置为: {combo}")
        except Exception as e:
            self.log(f"截图快捷键设置失败: {e}")

    def register_screenshot_listener(self):
        """注册截图快捷键监听"""
        if not HotkeyManager.is_supported():
            return

        try:
            if self.screenshot_hotkey_var.get().strip():
                result = self.hotkey_manager.register_screenshot_listener(
                    self.screenshot_hotkey_var.get(),
                    self.on_screenshot_hotkey_triggered,
                )
                if result:
                    self.processor.screenshot_hotkey_isNull = (
                        False  # 标记已注册截图快捷键
                    )
                    # 分割快捷键字符串并填充到输入框
                    parts = self.screenshot_hotkey_var.get().strip().split("+")
                    for i in range(1, 4):
                        entry = getattr(self, f"sk{i}")
                        entry.delete(0, tk.END)
                        if i <= len(parts) and parts[i - 1]:
                            entry.insert(0, parts[i - 1].lower())

                    self.log(f"已注册截图监听: {self.screenshot_hotkey_var.get()}")
                else:
                    self.log("注册截图监听失败")
        except Exception as e:
            self.log(f"注册截图监听失败: {e}")

    def unregister_screenshot_listener(self):
        """取消截图快捷键监听"""
        if not HotkeyManager.is_supported():
            return

        try:
            self.hotkey_manager.unregister_screenshot_listener()
            self.processor.screenshot_hotkey_isNull = True
        except Exception:
            pass

    def on_screenshot_hotkey_triggered(self):
        """截图快捷键触发回调"""
        # 延迟一小段时间，确保截图已经保存到剪贴板
        if self.running_state:
            self.processor.screenshot_hotkey_triggered = True
            self.log("检测到截图快捷键触发")
            # 60s 后重置 screenshot_hotkey_triggered 标志
            threading.Timer(
                60,
                lambda: setattr(self.processor, "screenshot_hotkey_triggered", False),
            ).start()

    def start_processing(self):
        self.processor.start()
        self.update_icon_status("success")
        self.running_state = True
        self.icon.menu = self.create_menu()  # 更新菜单
        self.log("已开始处理")

    def stop_processing(self):
        self.processor.stop()
        if self.icon:
            self.icon.icon = self.icon_image["processing"]  # 改用 'processing' 状态
        self.running_state = False
        self.icon.menu = self.create_menu()  # 更新菜单
        self.log("已停止处理")

    def create_tray_icon(self):
        base_icon = self.create_capsule_icon("grey")
        self.icon_image = {
            "processing": self.create_capsule_icon("grey"),
            "success": self.create_capsule_icon("green"),
            "error": self.create_capsule_icon("red"),
        }
        self.icon = pystray.Icon("name", base_icon, "PillOCR")
        self.icon.menu = self.create_menu()
        # hand control of the AppKit run loop back to Tkinter
        if platform.system() == "Darwin" and hasattr(self.icon, "run_detached"):
            self.icon.run_detached()
        else:
            threading.Thread(target=self.icon.run, daemon=True).start()

    def create_menu(self):
        """创建托盘菜单"""
        return pystray.Menu(
            pystray.MenuItem(
                "停止" if self.running_state else "启动",  # 使用 self.running_state
                self.toggle_processing,
            ),
            pystray.MenuItem("设置", self.show_window),
            pystray.MenuItem("退出", self.quit_app),
        )

    def toggle_processing(self, icon=None, item=None):
        """切换启动/停止状态"""
        if self.running_state:
            self.stop_processing()
        else:
            self.start_processing()
        # 更新菜单
        self.icon.menu = self.create_menu()

    def create_capsule_icon(self, color):
        scale = 4
        base_width, base_height = 24, 24
        width, height = base_width * scale, base_height * scale

        image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)

        if color == "grey":
            fill = (128, 128, 128, 255)
        elif color == "green":
            fill = (0, 255, 0, 255)
        elif color == "red":
            fill = (255, 0, 0, 255)
        else:
            fill = (0, 255, 0, 255)  # 默认使用绿色

        capsule_height = 12 * scale
        capsule_width = 24 * scale

        x = (width - capsule_width) // 2
        y = (height - capsule_height) // 2

        draw.ellipse(
            [x, y, x + capsule_height, y + capsule_height], fill=fill, outline=None
        )
        draw.ellipse(
            [
                x + capsule_width - capsule_height,
                y,
                x + capsule_width,
                y + capsule_height,
            ],
            fill=fill,
            outline=None,
        )
        draw.rectangle(
            [
                x + capsule_height // 2,
                y,
                x + capsule_width - capsule_height // 2,
                y + capsule_height,
            ],
            fill=fill,
            outline=None,
        )

        image = image.resize((base_width, base_height), Image.Resampling.LANCZOS)

        return image

    def hide_window(self):
        self.root.withdraw()

    def show_window(self):
        self.root.deiconify()

    def quit_app(self):
        self.unregister_hotkey()  # 取消热键注册
        self.unregister_screenshot_listener()  # 取消截图监听
        self.processor.stop()
        if self.icon:
            self.icon.stop()
        self.root.destroy()  # 修改为 destroy 以立即关闭窗口和主循环

    def update_icon_status(self, status):
        if hasattr(self, "icon") and self.icon and self.icon._running:
            try:
                self.icon.icon = self.icon_image[status]  # 直接设置图标
            except Exception as e:
                print(f"更新图标失败: {e}")

    def send_notification(self, status: str, message: str):
        """发送系统通知

        Args:
            status: 'success', 'error' 或 'info'
            message: 通知内容
        """
        if not self.notification_enabled_var.get():
            return
        if status == "success":
            self.notification_manager.notify_success(message)
        elif status == "error":
            self.notification_manager.notify_error(message)
        elif status == "info":
            self.notification_manager.notify("提示", message)

    def update_client_settings(self):
        """更新 ImageToMarkdown 处理器的设置"""
        current_provider = self.provider_var.get()
        settings = self.provider_settings.get(current_provider, {})

        # 更新API Key
        self.processor.set_api_key(settings.get("api_key", ""))

        # 更新代理
        self.processor.set_proxy(settings.get("proxy", ""))

        # 更新模型
        if current_provider == "OPENAI":
            self.processor.set_gpt_model(settings.get("model", "gpt-4o"))
        elif current_provider == "火山引擎":
            self.processor.set_gpt_model(settings.get("model", ""))
        elif current_provider == "自定义":
            self.processor.set_gpt_model(settings.get("model", ""))

        # 更新Prompt&Token 设置
        prov_cfg = settings.get("prompt_settings", {})
        self.processor.set_prompts(
            prov_cfg.get(
                "system_prompt",
                "You are a helpful assistant that converts images to markdown format. If the image contains mathematical formulas, use LaTeX syntax for them. Return only the markdown content of the image, without any additional words or explanations.",
            ),
            prov_cfg.get("user_prompt", "Here is my image."),
        )
        self.processor.set_max_tokens(int(prov_cfg.get("max_tokens", 1000)))
        self.processor.set_timeout(int(prov_cfg.get("timeout", 60)))

    def apply_provider_settings(self):
        """处理和切换服务商相关的 UI 界面更新和组件显示"""
        current_provider = self.provider_var.get()
        settings = self.provider_settings.get(current_provider, {})

        # 更新处理器的服务商
        if current_provider == "OPENAI":
            self.processor.set_provider("OPENAI")
        elif current_provider == "火山引擎":
            self.processor.set_provider("火山引擎")
        elif current_provider == "自定义":
            self.processor.set_provider("自定义")

        # —— 公共：所有服务商通用的 API Key 和 代理 UI 更新 ——
        self.api_key_var.set(settings.get("api_key", ""))
        self.proxy_var.set(settings.get("proxy", ""))

        # —— 各服务商特有的 UI 布局 ——
        # 隐藏所有模型/接入点/自定义 URL 区块
        self.model_frame.pack_forget()
        self.model_entry_frame.pack_forget()
        self.endpoint_frame.pack_forget()
        self.custom_url_frame.pack_forget()

        if current_provider == "OPENAI":
            # OpenAI：显示模型下拉
            self.model_var.set(settings.get("model", "gpt-4o"))
            self.model_frame.pack(after=self.provider_frame, fill=tk.X, pady=(0, 10))
        elif current_provider == "火山引擎":
            # 火山引擎：显示接入点输入
            self.model_var.set(settings.get("model", ""))
            self.endpoint_frame.pack(after=self.provider_frame, fill=tk.X, pady=(0, 10))
        elif current_provider == "自定义":
            # 自定义：URL + 模型输入
            self.url_var.set(settings.get("url", ""))
            self.model_var.set(settings.get("model", ""))
            self.custom_url_frame.pack(
                after=self.provider_frame, fill=tk.X, pady=(0, 10)
            )
            self.model_entry_frame.pack(
                after=self.custom_url_frame, fill=tk.X, pady=(0, 10)
            )

        # 同步 Prompt & Token
        prov_cfg = settings.get("prompt_settings", {})
        sys_txt = prov_cfg.get("system_prompt", self.processor.system_prompt)
        usr_txt = prov_cfg.get("user_prompt", self.processor.user_prompt)
        max_t = prov_cfg.get("max_tokens", self.processor.max_tokens)
        timeout_t = prov_cfg.get("timeout", self.processor.timeout)

        # 更新多行文本框
        self.system_text.delete("1.0", tk.END)
        self.system_text.insert("1.0", sys_txt)
        self.user_text.delete("1.0", tk.END)
        self.user_text.insert("1.0", usr_txt)
        # 更新 max_tokens 输入框
        self.max_tokens_var.set(max_t)
        # 更新 timeout 输入框
        self.timeout_var.set(timeout_t)

        # 确保在应用设置时更新客户端
        self.update_client_settings()

    # def save_prompt_settings(self):
    #     prompts = {
    #         'system_prompt': self.system_prompt_var.get(),
    #         'user_prompt':   self.user_prompt_var.get(),
    #         'max_tokens':    self.max_tokens_var.get()
    #     }
    #     self.processor.set_prompts(prompts['system_prompt'], prompts['user_prompt'])
    #     self.processor.set_max_tokens(prompts['max_tokens'])
    #     # 持久化到配置
    #     cfg = self.config_manager.load() or {}
    #     cfg.setdefault('prompt_settings', {}).update(prompts)
    #     self.config_manager.save(cfg)
    #     self.log("Prompt & Max Tokens 设置已保存")

    def save_settings(self):
        """保存所有设置"""
        display_provider = self.provider_var.get()
        current_provider = self.PROVIDER_REVERSE_MAPPING[display_provider]

        if current_provider == "OPENAI":
            settings = {
                "api_key": self.api_key_var.get().strip(),
                "proxy": self.proxy_var.get().strip(),
                "model": self.model_var.get().strip(),
            }
        elif current_provider == "火山引擎":
            settings = {
                "api_key": self.api_key_var.get().strip(),
                "proxy": self.proxy_var.get().strip(),
                "model": self.model_var.get().strip(),
            }
        elif current_provider == "自定义":
            # 保存自定义URL
            settings = {
                "url": self.url_var.get().strip(),
                "api_key": self.api_key_var.get().strip(),
                "proxy": self.proxy_var.get().strip(),
                "model": self.model_var.get().strip(),
            }

        self.provider_settings[current_provider] = settings

        # 保存 LaTeX 包装符
        latex_cfg = {
            "inline_wrapper": self.inline_var.get(),
            "block_wrapper": self.block_var.get(),
        }

        # prompt_settings
        self.provider_settings[current_provider].setdefault("prompt_settings", {})
        self.provider_settings[current_provider]["prompt_settings"].update(
            {
                "system_prompt": self.system_text.get("1.0", "end-1c").strip(),
                "user_prompt": self.user_text.get("1.0", "end-1c").strip(),
                "max_tokens": self.max_tokens_var.get(),
                "timeout": self.timeout_var.get(),
            }
        )

        # 构造最终要写入的 config
        config = {
            "current_provider": current_provider,
            "provider_settings": self.provider_settings,
            "latex_settings": latex_cfg,
            "hotkey": self.hotkey_var.get(),
            "screenshot_hotkey": self.screenshot_hotkey_var.get(),
            "process_pre_exist_image": self.process_pre_exist_image_var.get(),
            "notification_enabled": self.notification_enabled_var.get(),
        }
        # 更新处理起始图片设置
        self.processor.process_pre_exist_image = config.get(
            "process_pre_exist_image", False
        )
        # 更新通知设置
        self.notification_manager.set_enabled(config.get("notification_enabled", True))
        try:
            self.config_manager.save(config)
            self.update_client_settings()
            self.send_notification("info", "设置已保存")
        except Exception as e:
            self.log(f"保存设置失败: {e}")
            self.send_notification("error", f"保存失败: {str(e)[:30]}")

    def load_settings(self):
        """从配置文件加载设置到内存"""
        try:
            config = self.config_manager.load() or {}
            # —— 先恢复 provider_settings 和 current_provider ——
            self.provider_settings = config.get(
                "provider_settings", self.provider_settings
            )
            current_provider = config.get("current_provider", "OPENAI")
            self.provider_var.set(current_provider)

            # 恢复 LaTeX 包装符
            latex_cfg = config.get("latex_settings", {})
            self.inline_var.set(latex_cfg.get("inline_wrapper", "$ $"))
            self.block_var.set(latex_cfg.get("block_wrapper", "$$ $$"))
            self.processor.set_wrappers(self.inline_var.get(), self.block_var.get())

            # 恢复热键相关设置
            self.hotkey_var.set(config.get("hotkey", "ctrl+shift+o"))
            self.screenshot_hotkey_var.set(config.get("screenshot_hotkey", ""))
            self.process_pre_exist_image_var.set(
                config.get("process_pre_exist_image", False)
            )
            self.processor.process_pre_exist_image = (
                self.process_pre_exist_image_var.get()
            )
            self.register_hotkey()
            self.register_screenshot_listener()

            # 恢复通知设置
            self.notification_enabled_var.set(config.get("notification_enabled", True))
            self.notification_manager.set_enabled(self.notification_enabled_var.get())

            # 从当前服务商配置里读取 prompt_settings
            prov_cfg = self.provider_settings.get(current_provider, {})
            prompts = prov_cfg.get(
                "prompt_settings",
                {
                    "system_prompt": self.processor.system_prompt,
                    "user_prompt": self.processor.user_prompt,
                    "max_tokens": self.processor.max_tokens,
                    "timeout": self.processor.timeout,
                },
            )
            self.system_prompt_var.set(prompts["system_prompt"])
            self.user_prompt_var.set(prompts["user_prompt"])
            self.max_tokens_var.set(
                prompts.get("max_tokens", self.processor.max_tokens)
            )
            self.timeout_var.set(prompts.get("timeout", self.processor.timeout))
            self.processor.set_prompts(prompts["system_prompt"], prompts["user_prompt"])
            self.processor.set_max_tokens(
                prompts.get("max_tokens", self.processor.max_tokens)
            )
            self.processor.set_timeout(prompts.get("timeout", self.processor.timeout))

            # 应用服务商 UI 和 client 设置
            self.apply_provider_settings()
        except Exception as e:
            self.log(f"加载配置失败: {e}")

    def on_provider_change(self, event=None):
        """切换服务商"""
        display_provider = self.provider_dropdown.get()
        self.provider_var.set(display_provider)  # 直接使用显示名称

        # 根据供应商设置不同的模型
        if display_provider == "OPENAI":
            self.model_dropdown["values"] = ["gpt-4o", "gpt-4o-mini"]
        else:
            self.model_dropdown["values"] = []

        # 默认选择列表中的第一个模型
        if self.model_dropdown["values"]:
            self.model_var.set(self.model_dropdown["values"][0])

        # 显示/隐藏自定义 URL 框
        if display_provider == "自定义":
            # 在 provider_frame 下方插入
            self.custom_url_frame.pack(
                after=self.provider_frame, fill=tk.X, pady=(0, 10)
            )
        else:
            self.custom_url_frame.pack_forget()

        # 加载新服务商配置
        self.apply_provider_settings()

        # 自动保存 current_provider 到配置文件
        cfg = self.config_manager.load() or {}
        cfg["current_provider"] = display_provider
        self.config_manager.save(cfg)

        self.log(f"已切换到 {display_provider} 服务")

    def save_custom_url(self):
        """保存自定义URL并更新设置"""
        self.save_settings()
        self.log(f"已保存自定义URL: {self.url_var.get()}")

    def save_api_key(self):
        """保存 API Key"""
        self.save_settings()
        self.log("API Key已保存")

    def save_proxy(self):
        """保存代理设置"""
        self.save_settings()
        self.log("代理设置已保存")

    def save_model_choice(self, event=None):
        """保存模型选择到配置文件"""
        model_choice = self.model_var.get()  # 获取当前选择的模型
        self.save_settings()
        self.log(f"模型已设置为: {model_choice}")

    # def save_auto_start_setting(self):
    #     """保存自动启动设置"""
    #     self.save_settings()
    #     status = "启用" if self.auto_start_var.get() else "禁用"
    #     self.log(f"自动启动设置已{status}")


if __name__ == "__main__":
    root = tk.Tk()
    root.geometry(
        "800x800+{}+{}".format(
            root.winfo_screenwidth() // 2 - 400,  # 水平居中
            root.winfo_screenheight() // 2 - 400,  # 垂直居中
        )
    )  # 调整窗口大小以适应新布局
    # 在创建窗口后立即隐藏
    root.withdraw()
    processor = ImageToMarkdown(None, None)
    app = App(root, processor)

    # 更新 processor 的引用
    processor.log_callback = app.log
    processor.app = app
    root.withdraw()
    root.mainloop()
