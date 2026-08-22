# 长音频使用本地切片提交 ASR

[腾讯录音文件识别](https://cloud.tencent.com/document/api/1093/37823)的本地上传限制为 5MB，而长文件入口要求公网 URL；KnowRealm-AI 将标准化音频切成严格小于 5MB 的有序 Ogg/Opus 片段，并由一个 ASR Job 顺序提交和合并结果。V1 不为此引入 COS、公开下载地址或额外云存储凭据；只有实测证明切片无法满足准确率或吞吐时才重新评估 URL 上传。
