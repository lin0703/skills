---
name: sql-query
description: 面向季度利润分析 demo 的查数技能。当用户用自然语言提问利润、毛利、净利、同比、环比、趋势等问题时，使用本技能解析问题、解析指标和部门别名、调用财务 MCP 工具生成 SQL、执行查询并返回表格结果。
---

# 查数技能

## 工作流

1. 先对原始问题调用 `parse_financial_query`。
2. 对第一个指标词调用 `resolve_synonym`。
3. 如果问题里包含部门，再调用 `resolve_dimension_value`。
4. 获取 `get_metric_definition`、`search_data_assets` 和 `get_table_schema`。
5. 按显式透传规则执行 `schema_linking`、`generate_query_spec`、`compile_sql`。
6. 把 `compile_sql` 产出的 `sql` 先送进 `validate_sql`，通过后再调用 `execute_sql`。
7. 返回标准化查询结果；需要表格展示时再调用 `render_table`。

## 显式透传矩阵

- `parse_financial_query.time_expression -> schema_linking.time_expression`
- `resolve_dimension_value` 的标准化结果 -> `schema_linking.dimension_values`
- `schema_linking.metric_mappings / dimension_mappings / time_mapping -> generate_query_spec`
- `generate_query_spec.query_spec -> compile_sql`
- `compile_sql.sql -> validate_sql -> execute_sql`

## 关键入参

- `parse_financial_query` 的 `context` 只有在确实需要补充上一轮结果时再传；推荐传对象，单字符串只作为兼容兜底。
- `search_data_assets` 的 `dimensions` 推荐传数组，例如 `["部门"]`；单个字符串虽然兼容，但优先数组写法。
- `schema_linking` 的 `dimension_values` 优先传列表，不要传裸字符串。
- 推荐写法：`[{"dimension_name":"部门","standard_value":"GNSS部","code":"1000"}]`
- 兼容写法：`{"部门":"1000"}`
- `time_expression` 必须直接透传 `parse_financial_query` 的返回值，不能省略，也不要自己改写。
- `generate_query_spec` 必须显式传 `metric_mappings`、`dimension_mappings`、`time_mapping`，不能只传 `filters` 或 `analysis_type`。
- `compile_sql` 必须显式传 `query_spec`，不能传空对象，也不能假设它会从上下文自动读取。
- 部门一旦已经解析出 `code`，后续查询过滤统一使用这个编码，不再优先用部门名称过滤。

## 前置检查

- 如果缺少 `time_expression`，必须停止并说明缺少 `parse_financial_query.time_expression`，不要继续调用 `schema_linking`。
- 如果缺少 `metric_mappings`、`dimension_mappings` 或 `time_mapping`，必须停止并说明缺少 `schema_linking` 输出，不能继续调用 `generate_query_spec`。
- 如果缺少 `query_spec`，必须停止并说明缺少 `generate_query_spec.query_spec`，不能继续调用 `compile_sql`。
- 不要用 `{}`、`null` 或缺字段请求去碰运气；要先指出是哪一个上游结果没有拿到。

## Demo 边界

- 只处理季度利润分析 demo。
- 只使用 `finance` 业务域和 `ads_finance_dept_profit_qtr` 这张表。
- 当前只支持 `部门` 这一个维度。
- 如果指标或部门无法明确命中，不要硬猜，要明确提示用户补充信息。

## 输出风格

- 优先给简洁结论，带上指标名、季度或季度区间、部门范围。
- 只有用户明确要求时才返回最终 SQL。
- 如果结果为空，要说明是哪一个季度或部门条件没有查到数据。
