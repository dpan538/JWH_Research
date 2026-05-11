# 第一轮扫描试点处理报告

- 项目目录: `<LOCAL_SOURCE_ROOT>/苏皖沪古籍县志调查/第一轮扫描`
- 试点文档数: 20
- 页/文本块记录数: 4111
- 已有文字记录数: 1836
- 需 OCR 记录数: 2275
- 已抽取文字字符数: 2260625

## 质量标记

- needs_ocr: 2275
- possible_blank_page: 22
- thin_text_layer: 95

## 抽取/文件问题

- archive_not_extracted_in_text_stage: 1

## 试点文档

- `swhgz_8ac060901a96` 盛泽镇志.pdf | searchable_pdf | records=176 | ocr=10 | chars=231443
- `swhgz_f4a9a18a5f20` 岳西卫生志.pdf | searchable_pdf | records=406 | ocr=13 | chars=305969
- `swhgz_7bb6b2710a31` 泰州方志考略.pdf | searchable_pdf | records=13 | ocr=0 | chars=16193
- `swhgz_32ffc1ff5554` 阜宁县土壤志.pdf | searchable_pdf | records=215 | ocr=91 | chars=70386
- `swhgz_842a00b22f4b` （道光）来安县志.pdf | searchable_pdf | records=519 | ocr=0 | chars=266499
- `swhgz_4c1c359217c6` 南京建置志（一）.pdf | partial_text_pdf | records=198 | ocr=197 | chars=133
- `swhgz_366454084eda` 安徽省志·纺织工业志.pdf | partial_text_pdf | records=386 | ocr=385 | chars=82
- `swhgz_004a021677a6` 近代上海地区方志经济史料选辑（1840—1949）.pdf | partial_text_pdf | records=404 | ocr=401 | chars=800
- `swhgz_56f4b0d92bf6` 上海地方志概述.pdf | partial_text_pdf | records=100 | ocr=98 | chars=265
- `swhgz_6a7cf18fdfc3` 兴化方言志.pdf | scanned_pdf | records=27 | ocr=27 | chars=0
- `swhgz_34aaf204b2c3` [光绪]重修安徽通志总目录.pdf | scanned_pdf | records=15 | ocr=15 | chars=0
- `swhgz_41e345749dec` 嘉定县志·方言.pdf | scanned_pdf | records=40 | ocr=40 | chars=0
- `swhgz_29ee7be00abe` 安徽方志考略.pdf | scanned_pdf | records=140 | ocr=140 | chars=0
- `swhgz_1678af90cf34` 灵岩志略.pdf | scanned_pdf | records=43 | ocr=43 | chars=0
- `swhgz_4156be344675` 江苏省交通志·公路篇(1978-2008) 道路运输（草.doc | doc | records=62 | ocr=0 | chars=134672
- `swhgz_321865661e46` 安徽省 枞阳县志.doc | doc | records=190 | ocr=0 | chars=439732
- `swhgz_3e8acdade16f` （上海市）静安区志（一）.doc | doc | records=59 | ocr=0 | chars=131743
- `swhgz_4ce3b5c5c31c` 江苏旧方志提要.doc | doc | records=303 | ocr=0 | chars=662708
- `swhgz_183d73f4dfa0` 江苏省志 文物志.pdf.baiduyun.p.downloading | qc_edge | records=815 | ocr=815 | chars=0
- `swhgz_b1898e92cfcb` 苏州市志 第一册.rar | qc_edge | records=0 | ocr=0 | chars=0

## 下一步

1. 人工检查 OCR 队列和 Markdown 阅读稿，确认页面切分与标签是否符合预期。
2. 为 OCR 接入页图渲染和中文 OCR 引擎，只对 `ocr_queue_pilot.jsonl` 中的试点页执行。
3. 试点校验通过后，再按批次扩展到全库，避免一次性处理 245,000 页。
