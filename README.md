<div align="center">
<img src="https://picsur.zzwu.xyz/i/f36fa6f7-59fd-4612-9955-41064f8b468e.jpg" style="width:80px; height:auto;" alt="image">
<h1>PillOCR</h1>
一个接近无感的OCR工具<br><br>
</div>

---

## 动机

现在已经有许多用于公式识别的工具，也有许多优秀的免费工具，如[SimpleTex](https://simpletex.cn/)等。
这些软件使用时往往需要经历打开软件窗口→截图或上传图像→复制识别结果并粘贴到编辑器的过程。
在连续写作时，重复上述操作难免觉得麻烦，且打开、关闭窗口的过程会打断写作思路。
有些软件可以设置截图识别且识别完成不自动打开窗口，但这样又无从得知识别是否已经完成。
于是我做了这个小工具，献给那些和我有同样感受的同学。

## 原理

本工具基于大模型api，其会检测剪贴板中的图片，将其自动发送给大模型，并将大模型的返回结果处理后粘贴到剪贴板中。

## 特点

- 轻量化。该工具本质上只是一个UI，并不会在本地进行图片识别，因此对电脑算力要求不高。使用本地模型识别的好处是完全免费，但有些时候我们日常携带的用来写作的机器未必有足够的算力。
- 价格便宜。现在许多大模型api的价格已经足够低。以火山引擎的Doubao-1.5-vision-lite为例，本工具设置max_tokens为1000，而Doubao-vision-pro-32kapi的价格为0.0045元/千tokens，即识别一张图约0.5分钱。且有些大模型api还会赠送免费额度。
- 比较稳定。不依赖于某一家提供的服务，如果某天你使用的大模型api提供商倒闭了，可以另换一家。

## 模型推荐

- 火山引擎的Doubao-1.5-vision-lite，若觉得精准度不够可以使用Doubao-1.5-vision-pro，价格比前者贵一倍。火山引擎赠送500,000tokens的免费额度。

因为火山引擎的免费额度我还没用完，所以暂无其他推荐。大家有推荐的模型可以告诉我，我会添加到此处。

## 同类型工具推荐

- [SimpleTex](https://simpletex.cn/)，该软件功能非常强大，支持在识别结果上直接编辑，且支持转化为MathML和Typst（话说我或许也可以在这个工具中加入该功能？）。
- [MixTeX](https://github.com/RQLuo/MixTeX-Latex-OCR)，离线OCR软件，完全免费，效果非常不错。如果机器性能还可以的话强烈推荐。
- [MinerU](https://mineru.net/)，适合将整本pdf批量转化为markdown，可用于构建RAG使用的知识库。配合[RAGFlow](https://github.com/infiniflow/ragflow)食用很香。
- [Mathpix](https://mathpix.com/)，老牌公式识别软件，就是免费额度略少。

## 未来计划

如果用的人比较多，我也许会用tauri重写该工具。可能会增加一些功能，比如：

- 支持MathML和Typst（刚刚想到）；
- 识别+翻译；
- 添加其他显示语言；
  但作者今年即将毕业，升学/工作还无着落，且Rust仍在学习中……因此短期内如果工具没有严重问题可能会暂时搁置该项目。

## 打赏支持

如果这个工具对您有帮助的话，就请我吃个鸡腿吧~

<img src="https://github.com/user-attachments/assets/a1105e53-13f6-4654-89fa-edfe878194e8" style="width:400px; height:auto;" alt="image">
