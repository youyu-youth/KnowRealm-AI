"""来源锚点域：跨域引用的统一挂靠结构（分片/笔记/消息 → 学习资产）。

锚点唯一入口：写入与查询一律经本模块 service（对标 search 模块先例），
其他模块不得直连 source_anchors / source_anchor_links 表。本期锚点表
零写入者（F1 仅结构就位；第一个写入者是后续 A1/A3/graph 升级票）。
"""
