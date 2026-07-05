# Repository Health Report

## Summary
- Total Python modules (active source tree): 254
- Duplicate module filenames: 8
- Dead code candidates: 43
- Orphan tests: 4
- Modules without tests: 90

## Duplicate modules
__init__.py, config.py, landing_page_generator.py, main.py, roi_tracker.py, run_daily_content_growth.py, telegram_publisher.py, utils.py

## Dead code candidates
- modules.affiliate_skills
- modules.auto_offer_importer
- modules.blog_article_data
- modules.category_page_builder
- modules.comparison_generator
- modules.comparison_page_builder
- modules.data_adapters
- modules.distribution_boost
- modules.hub_page_builder
- modules.intent_page_generator
- modules.money_content_builder
- modules.pricing_page_builder
- modules.priority_page_builder
- modules.programmatic_page_utils
- modules.quick_reply_finder
- modules.review_page_builder
- modules.seo_expansion_pages
- modules.site_stats
- modules.social_policy_checker
- modules.social_posting_connectors

## Orphan tests
- scripts/test_click_webhook.py
- tests/test_breadcrumb_integrity.py
- tests/test_faq_schema_integrity.py
- tests/test_parser_scorer.py

## Modules without tests
- modules.action_priority
- modules.ads_generator
- modules.affiliate_links
- modules.affiliate_skills
- modules.affiliate_tracking
- modules.ai_angle_generator
- modules.auto_offer_importer
- modules.bilingual_site
- modules.blog_article_data
- modules.canonical_routes
- modules.community_discovery
- modules.comparison_generator
- modules.competitor_ads_spy
- modules.compliance_checker
- modules.content_approval
- modules.content_growth_pipeline
- modules.content_operations
- modules.content_planner
- modules.content_strategy
- modules.csv_exporter
- modules.ctr_title_engine
- modules.data_adapters
- modules.data_sources
- modules.distribution_boost
- modules.facebook_meta
- modules.geo_analyzer
- modules.gsc_404_recovery
- modules.homepage_crawl_sections
- modules.hub_page_builder
- modules.indexing_policy
- modules.intent_page_generator
- modules.internal_linker
- modules.keyword_analyzer
- modules.landing_page_generator
- modules.legacy_slug_normalizer
- modules.markdown_publisher
- modules.market_analyzer
- modules.money_content_builder
- modules.morning_dashboard
- modules.offer_loader

## Biggest files
- modules/vietnamese_localizer.py (216803 bytes)
- dashboard/app.py (213361 bytes)
- modules/site_builder.py (194137 bytes)
- scripts/generate_video_assets.py (160828 bytes)
- modules/social_distribution.py (89729 bytes)
- modules/money_content_builder.py (73171 bytes)
- modules/review_page_builder.py (72184 bytes)
- modules/audience_growth.py (68506 bytes)
- modules/trust_localization_upgrade.py (65491 bytes)
- modules/landing_page_generator.py (53524 bytes)
- scripts/create_today_ai_coding_articles.py (52581 bytes)
- modules/blog_article_data.py (48458 bytes)
- modules/content_operations.py (46720 bytes)
- modules/comparison_page_builder.py (42834 bytes)
- modules/social_publisher.py (41226 bytes)

## Dependency graph
- main.py -> action_priority, ads_generator, affiliate_links, affiliate_tracking, ai_angle_generator, audience_growth, bilingual_site, community_discovery, competitor_ads_spy, compliance_checker, content_approval, csv_exporter, data_sources, decision_engine, facebook_meta, geo_analyzer, gsc_performance, internal_linker, keyword_analyzer, keyword_intelligence, landing_page_generator, markdown_publisher, market_analyzer, offer_loader, offer_scorer, post_deploy_kit, profit_simulator, report_generator, review_workflow, roi_tracker, scheduler_runner, seo_system, seo_technical_cleanup, seo_title_optimizer, site_builder, sitemap_generator, social_content_generator, social_distribution, social_publish_queue, social_publisher, social_seo_exporter, structured_data_upgrade, trust_localization_upgrade
- build_site.py -> bilingual_site, canonical_routes, content_approval, facebook_meta, gsc_404_recovery, homepage_crawl_sections, internal_linker, legacy_slug_normalizer, seo_ai_search_upgrade, seo_metadata_uniqueness, seo_technical_cleanup, seo_title_optimizer, sitemap_generator, structured_data_upgrade, topical_hubs, trust_localization_upgrade
- apply_manual_redirects.py -> site_builder
- build_business_intelligence_dashboard.py -> business_intelligence, ceo_phase2
- build_ceo_dashboard.py -> opportunity_forecast, performance_tracking
- build_content_clusters.py -> content_operations, performance_tracking
- build_content_intelligence_dashboard.py -> business_intelligence, content_intelligence
- build_executive_dashboard.py -> performance_tracking
- build_internal_link_plan.py -> performance_tracking
- build_money_ranking.py -> content_operations, performance_tracking
- build_phase2_ceo_dashboard.py -> ceo_phase2
- check_duplicate_topics.py -> content_operations, performance_tracking

## Circular imports
- None detected by simple scan

## Unsafe imports
- modules.content_approval
- modules.markdown_publisher
- modules.review_workflow
- modules.site_builder
- modules.topic_expansion
- modules.website_publisher

## Modules touching docs/
- modules.quick_reply_finder
- modules.site_builder
- modules.vietnamese_localizer
- scripts.create_today_ai_coding_articles
- scripts.sync_site_output_to_docs

## Modules touching site_output/
- build_site
- config
- dashboard.app
- main
- modules.affiliate_tracking
- modules.ai_trend_discovery
- modules.audience_growth
- modules.bilingual_site
- modules.blog_article_data
- modules.comparison_page_builder
- modules.content_approval
- modules.content_growth_pipeline
- modules.gsc_404_recovery
- modules.keyword_intelligence
- modules.markdown_publisher
- modules.post_deploy_kit
- modules.priority_page_builder
- modules.review_workflow
- modules.seo_system
- modules.site_builder
- modules.sitemap_generator
- modules.social_distribution
- modules.social_draft_generator
- modules.trust_localization_upgrade
- modules.vietnamese_localizer
- scripts.apply_manual_redirects
- scripts.audit_404_urls
- scripts.audit_canonical_routing
- scripts.audit_seo_ai_search_2026
- scripts.bulk_mark_uploaded

## Modules touching build pipeline
- dashboard.app
- modules.audience_growth
- modules.content_growth_pipeline
- modules.post_deploy_kit
- scripts.bulk_mark_uploaded
- scripts.inject_youtube_links_from_csv
- scripts.mark_uploaded
- scripts.run_daily_content_growth
- scripts.update_youtube_links
- scripts.validate_category_pages
- scripts.validate_content_quality
- scripts.validate_go_pages
- scripts.validate_internal_links
- scripts.validate_navigation_pages
- scripts.validate_pricing_pages
- scripts.validate_site

## Modules touching Cloudflare
- build_site
- modules.seo_technical_cleanup
- modules.site_builder
- scripts.create_new_niche_reviews_batch
- scripts.deploy_cloudflare
- scripts.gsc_indexing_audit
- scripts.post_deploy
- scripts.validate_technical_seo

## Suggested refactor order
1. modules/content_strategy.py
2. modules/topic_scorer.py
3. modules/topic_ranker.py
4. modules/content_planner.py
5. modules/seo_technical_cleanup.py
6. modules/structured_data_upgrade.py
7. modules/internal_linker.py
