---
name: insurance-inquiry
description: 依据保险知识库查询保障范围、等待期和理赔材料，资料不足时转人工核实。
version: "1.0"
required-tools:
  - knowledge_search
  - calculator
  - memory_search
---

# 保险资料查询

## 必要输入

先明确用户要查询的产品、保障事项或理赔问题。缺少关键对象时先追问，不要自行补全。

## 执行步骤

1. 使用 `knowledge_search` 查询正式资料。
2. 需要精确换算时使用 `calculator`，不要心算关键数字。
3. 只有用户明确询问历史偏好或此前任务时才使用 `memory_search`。
4. 先给结论，再列依据，最后说明仍需人工核实的部分。

## 边界

工具是否可用由数字员工配置和系统策略决定。不要编造费率、收益或理赔结论。资料不足或相互冲突时停止推断，建议人工核实。
