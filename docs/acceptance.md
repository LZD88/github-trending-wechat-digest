# OpenSpec 场景验收矩阵

本页把 `add-wechat-github-trending-digest` 的每个规格场景映射到自动化测试。测试名称变化时必须同步更新本页；`tests/test_acceptance_matrix.py` 会检查是否遗漏场景。

## github-trending-digest

| Scenario | 自动化证据 |
|---|---|
| 正常定时生成 | `test_workflow_schedules_shanghai_0800_and_supports_manual_modes`、`test_pipeline_orders_stages_and_persists_results` |
| 定时任务延迟执行 | `test_scheduled_capture_keeps_previous_date_when_delayed_past_midnight`、`test_scheduled_capture_rejects_later_data` |
| 数据源返回至少十个有效仓库 | `test_orchestrator_prefers_primary_and_keeps_first_ten`、`test_end_to_end_local_http_stub_and_idempotent_second_run` |
| 有效仓库不足十个 | `test_orchestrator_warns_when_fewer_than_ten_are_available` |
| 项目元数据完整 | `test_enricher_uses_token_and_updates_metadata` |
| 可选元数据缺失 | `test_enricher_preserves_existing_values_when_fields_are_missing`、`test_enricher_degrades_on_api_failure_without_dropping_entry` |
| 仓库身份不可解析 | `test_parse_trending_html_skips_invalid_repository_identity` |
| 原简介为中文 | `test_contains_chinese_and_preserves_chinese_description` |
| 英文简介成功转换 | `test_batch_summarizes_english_descriptions` |
| 摘要服务不可用 | `test_summary_failure_falls_back_to_original`、`test_non_chinese_model_output_is_rejected` |
| 主数据源成功 | `test_end_to_end_local_http_stub_and_idempotent_second_run` |
| 主数据源失败但备用源有效 | `test_orchestrator_uses_fallback_when_primary_fails`、`test_fallback_accepts_fresh_payload` |
| 所有来源均不可验证 | `test_fallback_rejects_stale_payload`、`test_orchestrator_raises_when_all_sources_fail` |
| 首次生成榜单 | `test_digest_store_round_trip_uses_date_path` |
| 相同榜期重复生成相同内容 | `test_digest_store_reuses_identical_snapshot` |
| 手动预览 | `test_preview_outputs_content_and_never_calls_delivery`、`test_pipeline_preview_does_not_require_delivery` |
| 指定榜期补发 | `test_resend_prefers_historical_snapshot_without_refetch`、`test_missing_snapshot_does_not_fetch_or_send` |

## personal-wechat-delivery

| Scenario | 自动化证据 |
|---|---|
| 有效 Server酱密钥 | `test_serverchan_success_returns_message_id_and_posts_form`、`test_end_to_end_local_http_stub_and_idempotent_second_run` |
| 缺少推送密钥 | `test_delivery_requires_serverchan_sendkey` |
| 运行日志记录请求失败 | `test_logging_filter_redacts_arguments_after_formatting` |
| 生成榜单归档 | `test_digest_snapshot_file_contains_no_secret_fields`、`test_versioned_project_files_do_not_contain_credential_shaped_values` |
| 测试发送成功 | `test_binding_success_records_message_id_and_context` |
| 测试发送失败 | `test_binding_failure_is_not_marked_verified` |
| 单条消息可容纳完整日报 | `test_render_single_message_contains_required_fields_and_links` |
| 日报超过单条限制 | `test_render_splits_only_between_complete_project_blocks` |
| 调度任务重复执行 | `test_successful_delivery_is_skipped_on_normal_rerun`、`test_end_to_end_local_http_stub_and_idempotent_second_run` |
| 用户明确补发 | `test_manual_resend_sends_again_and_links_original` |
| 服务暂时不可用后恢复 | `test_temporary_failure_retries_with_backoff_then_succeeds`、`test_timeout_is_retryable` |
| 密钥无效 | `test_authentication_failure_is_not_retried` |
| 重试耗尽 | `test_retries_stop_after_three_attempts` |
| 使用默认提供方 | `test_preview_configuration_does_not_require_sendkey`、`test_serverchan_success_returns_message_id_and_posts_form` |
| 配置未知提供方 | `test_unknown_provider_lists_supported_values` |

