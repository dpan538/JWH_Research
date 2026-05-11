# Sample Audit Overview

这个 audit pack 用于人工抽查六个主题索引的准确性。它不会改变任何抽取规则，也不会运行 OCR；它只是把现有索引中的样本整理成便于人工判断的表单。

## How to Use

1. 逐个打开下面六个 sample audit 文件。
2. 对每条样本查看实体词、页码、原文件名和 context_snippet。
3. 在 `Manual judgement` 下填写 yes / no / uncertain。
4. 如果实体本身正确但类别过粗或上下文来自目录页，请在 notes 里说明。
5. 审完后，把 no / uncertain 的模式汇总，优先修正会影响全库扩展的规则。

## Why This Matters Before Full-Corpus OCR Expansion

Pilot 索引目前已经具备来源追溯，但自动抽取仍可能包含三类问题：通用词被当作实体、目录页造成类目噪音、以及 OCR/文本层残留导致上下文不完整。
在投入 full-corpus OCR 之前，人工样本审计可以判断哪些索引规则已经足够稳定，哪些规则需要先收紧。这样可以避免把 OCR 成本花在会放大噪音的抽取流程上。

## Sample Files

| Index | Total entries | Sampled entries | Audit sheet |
| --- | ---: | ---: | --- |
| `place_index` | 1832 | 30 | `place_index_sample_audit.md` |
| `person_index` | 229 | 30 | `person_index_sample_audit.md` |
| `transport_index` | 249 | 30 | `transport_index_sample_audit.md` |
| `dialect_index` | 20 | 20 | `dialect_index_sample_audit.md` |
| `custom_index` | 107 | 30 | `custom_index_sample_audit.md` |
| `relic_index` | 252 | 30 | `relic_index_sample_audit.md` |

Sampling is reproducible with fixed seed `20260511`. If an index has fewer than 30 rows, all rows are included.