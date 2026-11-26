# 回归测试映射（chongji）

每个已关闭的问题都对应到具体的测试名，谁改了相关代码，测试会先叫。

| Issue | 问题 | 钉住它的测试 |
| --- | --- | --- |
| #6 | 「2岁3个月」被算成 3 个月,阶段判成幼年 | `test_integration.TestRules::test_age_years_plus_months`、`TestRules::test_age_single_forms_unchanged`、`TestCli::test_case01_stage_is_adult` |
| #7 | 「上次 14.6kg,今天 13.4kg」当下体重被取成上次值 | `test_integration.TestRules::test_previous_weight_is_not_current`、`TestRules::test_previous_only_falls_back_with_note`、`TestHttp::test_care_reads_current_weight`、`TestCli::test_case03_weight_loss_alert` |
| #8 | 正文克数与公式克数不一致 | `test_integration.TestRules::test_grams_match_formula` |
| #9 | 「吐毛球」判成「无明确症状」 | `test_integration.TestRules::test_hairball_is_observe` |

## 为什么这样对应

- **#6** 两边都钉：`2岁3个月 == 27` 正向钉住叠加逻辑，`3个月 / 2岁 / 1.5岁` 反向钉住"别把单写岁或单写月改坏"。再加一条 CLI 端到端——
  `Python` 里 `age_months` 对了但 `stage()` 用错月份，单测是看不出来的，只有跑 `examples/case-01.txt` 看到「月龄:27 / 成体已绝育 / 每日 91 g」才闭环。
- **#7** 分三层：`weight_kg` 只认当下、`prev_weight` 单独取基准、`analyze` 在不给当下体重时不假装有趋势而是要加一条注。
  最后一层很重要——如果只修"取当下"，那么「只写了上次体重」的描述会变成 `weight=None`、喂食量整段消失，等于把一个 bug 换成另一个 bug。
- **#8** 用正则从公式尾部抠出 `= N g` 与 `plan["grams"]` 比。不直接断言 `119`：那是某个体重下的偶然值，换个食物密度就变。
- **#9** 同一组里放了三条：吐毛球→先观察、吐血→立即就医、吐了两次→24 小时内。只钉第一条会让人以为往症状表里加词很安全，实际上最容易的回归就是把"呕吐"这种词顺手塞进红旗档。

## 其它被测试钉住的口径

| 口径 | 测试 |
| --- | --- |
| 零依赖 HTTP 服务能起、页面含「宠记」与「开始评估」 | `TestHttp::test_index_page` |
| `/api/status` 在 `--mock` 下返回 `{"mock": true, "model": null}` | `TestHttp::test_status_is_mock` |
| POST 记账落库、`/api/care` 返回 `saved_id` | `TestHttp::test_records_persisted` |
| 描述为空时给「信息不足」而不是报错 | `TestHttp::test_care_empty_text`、`TestCli::test_empty_input_exit_2` |
| 标准输入当描述用（不传 `--text` / `--file`） | `TestCli::test_stdin_input` |
| 模型层 schema 是本仓自己的 `summary / care_tips / risks` | `TestRules::test_offline_layers_by_schema` |
| 四份真实描述各自的结论分支 | `examples/out/*.md` + `TestCli` 里的三条端到端 |
