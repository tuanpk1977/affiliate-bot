"""Hand-written supporting blog article data for the AI coding workflow cluster."""

from __future__ import annotations


SUPPORTING_BLOG_ARTICLES = {
    "windsurf-prompt-checklist": {
        "title": "Windsurf Prompt Checklist",
        "summary": "A practical checklist I use before sending a coding prompt to Windsurf, with examples for safer first builds.",
        "vi_title": "Checklist prompt Windsurf",
        "vi_summary": "Checklist thực tế tôi dùng trước khi gửi prompt lập trình cho Windsurf, kèm ví dụ để bản build đầu an toàn hơn.",
        "eyebrow": "Prompt checklist | AI coding workflow | Last updated",
        "vi_eyebrow": "Checklist prompt | Quy trình AI coding | Cập nhật",
        "h1": "Windsurf Prompt Checklist: What I Check Before Sending a Task",
        "vi_h1": "Checklist prompt Windsurf: tôi kiểm tra gì trước khi gửi task",
        "intro": [
            "Windsurf is fast when the prompt is clear. When the prompt is vague, it can still move quickly, but the first build usually contains the wrong assumptions. I have seen this happen with static pages, bilingual content, sitemap updates, and small dashboard features.",
            "This checklist is the process I use before sending a task to Windsurf. It is connected to my main guide on ChatGPT prompts for Windsurf, but this page is more practical: what to prepare, what to include, what to avoid, and how to make the first build easier to test.",
            "The goal is not to make Windsurf perfect. The goal is to reduce avoidable cleanup. A good prompt makes it easier for Windsurf to build the first version and easier for me to hand focused repair work to Codex if something breaks.",
        ],
        "vi_intro": [
            "Windsurf rất nhanh khi prompt rõ. Nhưng nếu prompt mơ hồ, nó vẫn có thể tạo bản đầu rất nhanh và kèm theo nhiều giả định sai. Tôi đã gặp chuyện này với static page, nội dung song ngữ, cập nhật sitemap và các tính năng dashboard nhỏ.",
            "Đây là checklist tôi dùng trước khi gửi task cho Windsurf. Nó liên quan trực tiếp đến bài chính về prompt ChatGPT cho Windsurf, nhưng bài này đi vào thực hành hơn: cần chuẩn bị gì, nên ghi gì, tránh gì và làm sao để bản build đầu dễ kiểm tra hơn.",
            "Mục tiêu không phải biến Windsurf thành công cụ hoàn hảo. Mục tiêu là giảm phần cleanup không cần thiết. Một prompt tốt giúp Windsurf dựng bản đầu sạch hơn và giúp tôi chuyển phần sửa tập trung sang Codex nếu có lỗi thật.",
        ],
        "sections": [
            {
                "id": "why-checklist",
                "heading": "Why I use a checklist before Windsurf",
                "vi_heading": "Vì sao tôi dùng checklist trước khi gửi cho Windsurf",
                "paragraphs": [
                    "When I first started using AI coding tools, I often sent Windsurf a rough idea and waited for the output. That worked for simple screens, but it created problems on real projects. The tool might create the right page in the wrong folder, update generated output instead of the source generator, or add a CTA that did not match the current routing system.",
                    "A checklist slows me down for five minutes. That sounds like friction, but it usually saves more time later. Before Windsurf touches the project, I want to know the page goal, the target files, the constraints, the internal links, the validation commands, and the expected final report.",
                    "This is especially useful on a static SEO site. A page can look fine in the browser while the sitemap, canonical URL, hreflang tags, or language version is wrong. The checklist keeps the task tied to the real publishing pipeline.",
                ],
                "vi_paragraphs": [
                    "Khi mới dùng AI coding tools, tôi thường gửi cho Windsurf một ý tưởng thô rồi chờ kết quả. Cách đó ổn với màn hình đơn giản, nhưng dễ gây lỗi trong dự án thật. Công cụ có thể tạo đúng trang nhưng sai thư mục, sửa output đã generate thay vì source generator, hoặc thêm CTA không khớp hệ thống route hiện tại.",
                    "Checklist khiến tôi chậm lại khoảng năm phút. Nghe có vẻ mất thời gian, nhưng thường tiết kiệm nhiều thời gian sửa lỗi sau đó. Trước khi để Windsurf chạm vào project, tôi muốn biết mục tiêu trang, file liên quan, ràng buộc, internal links, lệnh validate và kiểu báo cáo cuối.",
                    "Điều này đặc biệt hữu ích với static SEO site. Một trang có thể nhìn ổn trên trình duyệt nhưng sitemap, canonical URL, hreflang hoặc bản ngôn ngữ lại sai. Checklist giữ task bám vào pipeline publish thật.",
                ],
            },
            {
                "id": "checklist-items",
                "heading": "The checklist I use",
                "vi_heading": "Checklist tôi đang dùng",
                "paragraphs": [
                    "My Windsurf checklist starts with the user goal. I write what the reader or user should be able to do after the change. For a blog article, the goal might be to learn a workflow and move to the main guide. For a bug fix, the goal might be to stop a code block from overflowing on mobile.",
                    "Next I list the source of truth. If the page is generated, I say clearly that the source generator should be changed, not only the generated HTML. If the route must appear in GitHub Pages, I mention both `site_output` and `docs` so the tool does not stop too early.",
                    "Then I add safety rules. My common rules are: do not deploy, do not call external APIs, do not create fake affiliate links, do not add secrets, do not enable auto-posting, and do not break `/go/` redirect behavior.",
                    "Finally, I include the test commands. The prompt should not end with just \"make the change.\" It should end with build, sync, validation, language integrity, go-page checks, and a short report. That makes the result easier to trust.",
                ],
                "vi_paragraphs": [
                    "Checklist Windsurf của tôi bắt đầu bằng mục tiêu người dùng. Tôi viết rõ sau thay đổi này người đọc hoặc người dùng phải làm được gì. Với một bài blog, mục tiêu có thể là hiểu workflow và đi tiếp sang bài chính. Với bug fix, mục tiêu có thể là chặn code block bị tràn trên mobile.",
                    "Tiếp theo tôi liệt kê nguồn đúng cần sửa. Nếu trang được generate, tôi ghi rõ phải sửa source generator, không chỉ sửa HTML đã sinh ra. Nếu route phải hoạt động trên GitHub Pages, tôi nhắc cả `site_output` và `docs` để công cụ không dừng quá sớm.",
                    "Sau đó tôi thêm quy tắc an toàn. Các quy tắc thường dùng là: không deploy, không gọi API ngoài, không tạo affiliate link giả, không thêm secret, không bật auto-posting và không phá hành vi redirect `/go/`.",
                    "Cuối cùng tôi đưa lệnh test. Prompt không nên kết thúc bằng câu \"hãy sửa\". Nó nên yêu cầu build, sync, validate, kiểm tra language integrity, kiểm tra go pages và báo cáo ngắn. Như vậy kết quả dễ tin hơn.",
                ],
            },
            {
                "id": "prompt-example-page",
                "heading": "Prompt example: create a supporting article",
                "vi_heading": "Ví dụ prompt: tạo bài hỗ trợ",
                "paragraphs": [
                    "When I ask Windsurf to create a supporting article, I do not only give the title. I describe the cluster, the main article, the internal links, and the content quality rules. This prevents the article from becoming an isolated page.",
                    "The prompt below is the kind of instruction I would send when building another page in this AI coding workflow cluster.",
                ],
                "vi_paragraphs": [
                    "Khi yêu cầu Windsurf tạo một bài hỗ trợ, tôi không chỉ đưa tiêu đề. Tôi mô tả cluster, bài chính, internal links và quy tắc chất lượng nội dung. Cách này tránh việc bài mới trở thành một trang rời rạc.",
                    "Prompt bên dưới là kiểu chỉ dẫn tôi sẽ gửi khi tạo thêm một trang trong cụm nội dung AI coding workflow này.",
                ],
                "code": "Create a supporting SEO blog article for /blog/chatgpt-prompts-for-windsurf/. Keep the current site style and bilingual pipeline. Add clear H1, intro, table of contents, practical sections, prompt examples, common mistakes, FAQ, related links, and CTA to the workflow checklist. Link naturally to /blog/chatgpt-prompts-for-windsurf/, /windsurf-review/, /comparisons/cursor-vs-windsurf/, and /free-ai-coding-workflow-checklist/. Do not add fake affiliate links, API calls, or auto-posting logic. Rebuild, sync docs, and run validation.",
            },
            {
                "id": "prompt-example-bug",
                "heading": "Prompt example: fix a specific issue",
                "vi_heading": "Ví dụ prompt: sửa một lỗi cụ thể",
                "paragraphs": [
                    "For bug fixes, I try to make the prompt narrower. Windsurf performs better when the task has a visible problem, a small set of likely files, and a definition of done.",
                    "This kind of prompt is useful when a page looks broken, but I do not yet know which CSS rule or generator function is responsible.",
                ],
                "vi_paragraphs": [
                    "Với bug fix, tôi cố làm prompt hẹp hơn. Windsurf xử lý tốt hơn khi task có lỗi hiển thị rõ, một nhóm file có khả năng liên quan và định nghĩa thế nào là xong.",
                    "Kiểu prompt này hữu ích khi một trang nhìn bị lỗi nhưng tôi chưa biết CSS rule hay generator function nào là nguyên nhân.",
                ],
                "code": "The blog page /blog/chatgpt-prompts-for-windsurf/ has long prompt examples inside pre/code blocks that overflow outside the article card. Inspect the shared article CSS in modules/site_builder.py and any generated blog page output. Fix the source CSS so pre, code, .prompt, and .code-block stay inside the content width on desktop and mobile. Do not change article content. Rebuild, sync docs, validate the site, and report the exact files changed.",
            },
            {
                "id": "mistakes",
                "heading": "Common prompt mistakes",
                "vi_heading": "Những lỗi prompt thường gặp",
                "paragraphs": [
                    "The biggest mistake is asking Windsurf to do strategy, writing, coding, SEO, tracking, and deployment cleanup in one vague instruction. It can try, but the result is harder to review.",
                    "The second mistake is not naming the files or pipeline. If a project generates `docs` from `site_output`, the prompt should say that. If Vietnamese pages are generated from English pages, the prompt should mention the localization pipeline.",
                    "The third mistake is skipping validation. A page is not done because it exists. It is done when links work, sitemap is updated, language integrity passes, and the page reads naturally.",
                ],
                "vi_paragraphs": [
                    "Lỗi lớn nhất là yêu cầu Windsurf làm chiến lược, viết nội dung, code, SEO, tracking và cleanup deploy trong một lệnh mơ hồ. Nó có thể thử làm, nhưng kết quả rất khó review.",
                    "Lỗi thứ hai là không nói rõ file hoặc pipeline. Nếu project generate `docs` từ `site_output`, prompt nên ghi điều đó. Nếu trang tiếng Việt được tạo từ trang tiếng Anh, prompt nên nhắc pipeline localization.",
                    "Lỗi thứ ba là bỏ qua validation. Một trang không phải đã xong chỉ vì nó tồn tại. Nó chỉ nên xem là xong khi link chạy, sitemap cập nhật, language integrity pass và nội dung đọc tự nhiên.",
                ],
            },
            {
                "id": "related-guides",
                "heading": "Related guides in this workflow",
                "vi_heading": "Các hướng dẫn liên quan trong workflow này",
                "paragraphs": [
                    "If you want the full process, start with my guide to ChatGPT prompts for Windsurf. If your problem is bilingual output, read the mixed-language guide next. If Windsurf creates the first version but the project still needs careful cleanup, use the Windsurf-to-Codex workflow.",
                    "These articles are meant to work together. One explains the prompt habit, one gives a checklist, one handles language problems, and one explains when to move from first build to focused repair.",
                ],
                "vi_paragraphs": [
                    "Nếu muốn xem toàn bộ quy trình, hãy bắt đầu với bài prompt ChatGPT cho Windsurf. Nếu vấn đề của bạn là output song ngữ, đọc tiếp bài xử lý lỗi lẫn ngôn ngữ. Nếu Windsurf đã tạo bản đầu nhưng project cần cleanup kỹ hơn, dùng bài workflow Windsurf sang Codex.",
                    "Các bài này được thiết kế để hỗ trợ nhau. Một bài giải thích thói quen viết prompt, một bài đưa checklist, một bài xử lý lỗi ngôn ngữ và một bài giải thích khi nào nên chuyển từ bản build đầu sang sửa tập trung.",
                ],
            },
        ],
        "faq": [
            ("What should I include in a Windsurf prompt?", "Include the goal, files or routes involved, constraints, examples, expected output, and validation commands."),
            ("Should I let Windsurf edit generated docs directly?", "Usually no. If the page is generated, fix the source generator first, then rebuild and sync docs through the normal pipeline."),
            ("How long should a Windsurf prompt be?", "Long enough to remove ambiguity. A practical prompt can be several paragraphs if it includes source files, safety rules, and tests."),
            ("Can beginners use this checklist?", "Yes. The checklist helps beginners describe the goal clearly even when they do not know every implementation detail."),
            ("How does this connect to Codex?", "The checklist improves the first Windsurf build. If the result still has bugs, the same notes help create a focused Codex repair prompt."),
        ],
        "vi_faq": [
            ("Nên ghi gì trong prompt cho Windsurf?", "Hãy ghi mục tiêu, file hoặc route liên quan, ràng buộc, ví dụ, kết quả mong muốn và lệnh validation."),
            ("Có nên để Windsurf sửa trực tiếp docs đã generate không?", "Thường là không. Nếu trang được generate, nên sửa source generator trước, sau đó rebuild và sync docs bằng pipeline hiện tại."),
            ("Prompt cho Windsurf nên dài bao nhiêu?", "Dài vừa đủ để giảm mơ hồ. Một prompt thực tế có thể dài vài đoạn nếu cần nêu file nguồn, quy tắc an toàn và test."),
            ("Người mới có dùng checklist này được không?", "Có. Checklist giúp người mới mô tả mục tiêu rõ hơn ngay cả khi chưa biết mọi chi tiết kỹ thuật."),
            ("Checklist này liên quan gì đến Codex?", "Checklist giúp bản build đầu của Windsurf sạch hơn. Nếu vẫn có lỗi, chính các ghi chú đó giúp tạo prompt sửa tập trung cho Codex."),
        ],
    },
    "fix-windsurf-mixed-language": {
        "title": "Fix Windsurf Mixed Language Issues",
        "summary": "How I fix mixed English and Vietnamese UI or content when Windsurf generates static site pages.",
        "vi_title": "Sửa lỗi lẫn ngôn ngữ khi dùng Windsurf",
        "vi_summary": "Cách tôi sửa lỗi lẫn tiếng Anh và tiếng Việt trong UI hoặc nội dung khi Windsurf generate static site.",
        "eyebrow": "Bilingual static sites | Windsurf debugging | Last updated",
        "vi_eyebrow": "Static site song ngữ | Debug với Windsurf | Cập nhật",
        "h1": "How to Fix Mixed English/Vietnamese Output from Windsurf",
        "vi_h1": "Cách sửa lỗi lẫn tiếng Anh và tiếng Việt khi Windsurf tạo site",
        "intro": [
            "Mixed language is one of the easiest AI-generated site problems to miss. A page can look mostly correct, but one heading says Contents, another button says Đọc bài đánh giá, and a comparison table mixes English sentences with Vietnamese labels.",
            "I have hit this problem while building bilingual static pages for MS Smile AI Review Hub. The fix is not to manually edit the generated HTML and hope it stays fixed. The fix is to trace where the text comes from, patch the source generator or localization layer, rebuild, and test both language versions.",
            "This guide explains the workflow I use when Windsurf creates a page that mixes English and Vietnamese. It supports the main article about ChatGPT prompts for Windsurf, because the best fix starts with a better debugging prompt.",
        ],
        "vi_intro": [
            "Lẫn ngôn ngữ là một trong những lỗi dễ bị bỏ sót nhất khi AI generate static site. Một trang có thể nhìn gần đúng, nhưng một heading vẫn là Contents, một nút lại là Đọc bài đánh giá, còn bảng so sánh trộn câu tiếng Anh với nhãn tiếng Việt.",
            "Tôi đã gặp lỗi này khi xây các trang static song ngữ cho MS Smile AI Review Hub. Cách sửa không phải là chỉnh thủ công HTML đã generate rồi hy vọng lần sau không hỏng. Cách đúng là truy nguồn text đến từ đâu, sửa source generator hoặc lớp localization, rebuild và kiểm tra cả hai bản ngôn ngữ.",
            "Bài này giải thích workflow tôi dùng khi Windsurf tạo page bị trộn tiếng Anh và tiếng Việt. Nó hỗ trợ bài chính về prompt ChatGPT cho Windsurf, vì cách sửa tốt thường bắt đầu bằng một prompt debug rõ hơn.",
        ],
        "sections": [
            {
                "id": "why-it-happens",
                "heading": "Why mixed language happens",
                "vi_heading": "Vì sao lỗi lẫn ngôn ngữ xảy ra",
                "paragraphs": [
                    "On a static site, text can come from many places: handwritten article content, navigation templates, footer templates, generated tables, FAQ schema, breadcrumbs, social labels, and localization replacements. Windsurf might fix the visible paragraph while leaving the table of contents or JSON-LD untouched.",
                    "The problem gets worse when English pages are the source and Vietnamese pages are generated later. If the localization layer only translates common UI words, a new article may keep English headings and body content under `/vi/` while only the menu is Vietnamese.",
                    "That is why I treat mixed language as a pipeline bug, not only a content bug. The question is not simply which words are wrong. The question is which source created those words and whether the next build will recreate the problem.",
                ],
                "vi_paragraphs": [
                    "Trong static site, text có thể đến từ nhiều nơi: nội dung bài viết, template navigation, footer, bảng generate tự động, FAQ schema, breadcrumb, nhãn social và các replacement trong localization. Windsurf có thể sửa đoạn văn đang thấy nhưng để sót mục lục hoặc JSON-LD.",
                    "Vấn đề nặng hơn khi trang tiếng Anh là nguồn và trang tiếng Việt được generate sau. Nếu lớp localization chỉ dịch vài UI word phổ biến, một bài mới trong `/vi/` có thể vẫn giữ heading và body tiếng Anh, trong khi menu đã là tiếng Việt.",
                    "Vì vậy tôi xem mixed language là lỗi pipeline, không chỉ lỗi nội dung. Câu hỏi không chỉ là từ nào sai, mà là nguồn nào đã tạo ra từ đó và lần build tiếp theo có tái tạo lỗi không.",
                ],
            },
            {
                "id": "inspection",
                "heading": "How I inspect the page",
                "vi_heading": "Tôi kiểm tra trang như thế nào",
                "paragraphs": [
                    "I start with the live or local URL and make a short list of every mixed-language area. I check the title, H1, table of contents, buttons, breadcrumbs, footer, FAQ, comparison tables, and code examples. Code examples can stay English if they are meant to be copied into Windsurf or Codex.",
                    "Then I compare English and Vietnamese routes. If `/blog/chatgpt-prompts-for-windsurf/` is English and `/vi/blog/chatgpt-prompts-for-windsurf/` is also mostly English, I know the issue is not the page template alone. It is probably the localization flow or missing page-specific translations.",
                    "I also inspect generated files in `site_output` and `docs`. If both are wrong, the source generator is likely wrong. If `site_output` is right but `docs` is wrong, the sync or deployment output may be stale.",
                ],
                "vi_paragraphs": [
                    "Tôi bắt đầu từ URL live hoặc local và ghi nhanh mọi khu vực bị lẫn ngôn ngữ. Tôi kiểm tra title, H1, mục lục, nút, breadcrumb, footer, FAQ, bảng so sánh và code example. Code example có thể giữ tiếng Anh nếu dùng để copy vào Windsurf hoặc Codex.",
                    "Sau đó tôi so sánh route tiếng Anh và tiếng Việt. Nếu `/blog/chatgpt-prompts-for-windsurf/` là tiếng Anh và `/vi/blog/chatgpt-prompts-for-windsurf/` cũng gần như tiếng Anh, vấn đề không chỉ nằm ở template trang. Khả năng cao là localization flow hoặc thiếu bản dịch riêng cho bài đó.",
                    "Tôi cũng kiểm tra file đã generate trong `site_output` và `docs`. Nếu cả hai đều sai, source generator có thể sai. Nếu `site_output` đúng nhưng `docs` sai, phần sync hoặc output deploy có thể đang cũ.",
                ],
            },
            {
                "id": "prompt-example",
                "heading": "Prompt example: ask Windsurf to trace the source",
                "vi_heading": "Ví dụ prompt: yêu cầu Windsurf truy nguồn lỗi",
                "paragraphs": [
                    "A good mixed-language prompt should tell Windsurf to trace the source instead of editing the final HTML only.",
                    "This is the kind of prompt I use when the Vietnamese page is not truly Vietnamese.",
                ],
                "vi_paragraphs": [
                    "Một prompt xử lý mixed-language tốt nên yêu cầu Windsurf truy nguồn lỗi, thay vì chỉ sửa HTML cuối.",
                    "Đây là kiểu prompt tôi dùng khi trang tiếng Việt chưa thật sự là tiếng Việt.",
                ],
                "code": "Inspect the English and Vietnamese versions of this static blog page. The /vi/ route still contains English headings, body copy, CTA labels, and table of contents items. Find whether the text comes from the source article template, localization module, generated docs, or sync pipeline. Fix the source generator/localizer, not only the generated HTML. Prompt/code blocks may remain English intentionally. Rebuild, sync docs, run language integrity validation, and report the files changed.",
            },
            {
                "id": "prompt-example-css",
                "heading": "Prompt example: protect code blocks while fixing text",
                "vi_heading": "Ví dụ prompt: giữ code block an toàn khi sửa text",
                "paragraphs": [
                    "Sometimes translation logic accidentally touches CSS or code. I have seen a replacement for the word Cons affect the font name Consolas. That is why I tell Windsurf which parts can remain English and which parts must be translated.",
                    "This prompt is useful when a localization fix could accidentally rewrite schema, CSS, code examples, or brand names.",
                ],
                "vi_paragraphs": [
                    "Đôi khi logic dịch vô tình chạm vào CSS hoặc code. Tôi từng gặp replacement cho từ Cons làm ảnh hưởng font name Consolas. Vì vậy tôi luôn nói rõ phần nào được giữ tiếng Anh và phần nào phải dịch.",
                    "Prompt này hữu ích khi một bản sửa localization có thể vô tình sửa schema, CSS, code example hoặc brand name.",
                ],
                "code": "Fix mixed language on the visible Vietnamese page only. Do not translate code blocks, prompt examples, CSS font names, schema property names, URL slugs, or product names like ChatGPT, Windsurf, Codex, Cursor, and GitHub Copilot. Translate H1, intro, headings, table of contents labels, CTA labels, FAQ, and normal paragraphs into natural Vietnamese. Confirm English pages remain English.",
            },
            {
                "id": "common-mistakes",
                "heading": "Common mistakes when fixing bilingual pages",
                "vi_heading": "Lỗi thường gặp khi sửa trang song ngữ",
                "paragraphs": [
                    "The first mistake is fixing only `docs`. That can make the live page look correct until the next build. If the source generator still contains the old text, the problem returns.",
                    "The second mistake is translating everything. Prompt examples, command names, CSS properties, JSON-LD schema keys, and product names should often remain English. Real localization is not blind replacement.",
                    "The third mistake is forgetting SEO tags. A visible Vietnamese article can still have an English meta description, breadcrumb schema, FAQ schema, or Open Graph title. That matters for search engines and social previews.",
                ],
                "vi_paragraphs": [
                    "Lỗi đầu tiên là chỉ sửa `docs`. Cách đó có thể làm live page nhìn đúng cho đến lần build tiếp theo. Nếu source generator vẫn chứa text cũ, lỗi sẽ quay lại.",
                    "Lỗi thứ hai là dịch mọi thứ. Prompt example, tên command, CSS property, JSON-LD schema key và tên sản phẩm thường nên giữ tiếng Anh. Localization thực tế không phải thay chữ mù quáng.",
                    "Lỗi thứ ba là quên SEO tag. Một bài tiếng Việt có thể nhìn đúng nhưng meta description, breadcrumb schema, FAQ schema hoặc Open Graph title vẫn là tiếng Anh. Điều đó ảnh hưởng đến search engine và social preview.",
                ],
            },
            {
                "id": "validation",
                "heading": "How I validate the fix",
                "vi_heading": "Tôi validate bản sửa như thế nào",
                "paragraphs": [
                    "After the fix, I rebuild the site, sync `site_output` to `docs`, and run language integrity checks. I also open the target pages in the browser because some problems are visual: a language switcher can overflow, a table can be too wide, or a prompt block can break the article card.",
                    "I check that the English page remains English and that the Vietnamese page uses natural Vietnamese. I also check internal links. A Vietnamese page should usually link to `/vi/` equivalents where they exist.",
                    "If everything passes, I commit the source files and the generated `docs` output needed for GitHub Pages. I do not commit logs or unrelated generated reports unless the task specifically requires them.",
                ],
                "vi_paragraphs": [
                    "Sau khi sửa, tôi rebuild site, sync `site_output` sang `docs` và chạy kiểm tra language integrity. Tôi cũng mở trang bằng trình duyệt vì một số lỗi là lỗi hiển thị: language switcher có thể tràn, bảng có thể quá rộng hoặc prompt block có thể phá card bài viết.",
                    "Tôi kiểm tra trang tiếng Anh vẫn là tiếng Anh và trang tiếng Việt dùng tiếng Việt tự nhiên. Tôi cũng kiểm tra internal links. Trang tiếng Việt thường nên link sang bản `/vi/` nếu có.",
                    "Nếu mọi thứ pass, tôi commit source files và output `docs` cần cho GitHub Pages. Tôi không commit logs hoặc report generate không liên quan trừ khi task yêu cầu.",
                ],
            },
            {
                "id": "related-guides",
                "heading": "Related guides",
                "vi_heading": "Hướng dẫn liên quan",
                "paragraphs": [
                    "For the broader prompt-writing process, read the main guide on ChatGPT prompts for Windsurf. If you want a quick preparation list before sending the task, use the Windsurf prompt checklist. If the first build works but still needs careful cleanup, continue with the Windsurf-to-Codex workflow.",
                ],
                "vi_paragraphs": [
                    "Để xem quy trình viết prompt đầy đủ hơn, hãy đọc bài chính về prompt ChatGPT cho Windsurf. Nếu bạn muốn danh sách chuẩn bị nhanh trước khi gửi task, dùng checklist prompt Windsurf. Nếu bản build đầu đã chạy nhưng vẫn cần cleanup kỹ, đọc tiếp workflow Windsurf sang Codex.",
                ],
            },
        ],
        "faq": [
            ("Why does Windsurf mix English and Vietnamese?", "It can happen when content, templates, and localization rules are generated from different sources or when the Vietnamese route only translates shared UI labels."),
            ("Should I manually edit the Vietnamese HTML?", "Only as a temporary inspection step. The durable fix should happen in the source generator or localization module."),
            ("Can prompt examples stay English on Vietnamese pages?", "Yes. If the prompt is meant to be copied into Windsurf or Codex, keeping it in English can be intentional and useful."),
            ("What should I test after fixing language issues?", "Check H1, title, meta description, table of contents, CTA labels, FAQ, schema, internal links, and browser layout."),
            ("How does this relate to ChatGPT prompts for Windsurf?", "A clear ChatGPT debugging prompt helps Windsurf fix the right source files instead of patching the wrong output."),
        ],
        "vi_faq": [
            ("Vì sao Windsurf trộn tiếng Anh và tiếng Việt?", "Điều này xảy ra khi nội dung, template và rule localization đến từ nhiều nguồn khác nhau, hoặc route tiếng Việt chỉ dịch vài UI label chung."),
            ("Có nên sửa thủ công HTML tiếng Việt không?", "Chỉ nên dùng để kiểm tra tạm thời. Bản sửa bền vững nên nằm trong source generator hoặc module localization."),
            ("Prompt example có thể giữ tiếng Anh trên trang tiếng Việt không?", "Có. Nếu prompt dùng để copy vào Windsurf hoặc Codex, giữ tiếng Anh là có chủ đích và hữu ích."),
            ("Sau khi sửa lỗi ngôn ngữ cần test gì?", "Kiểm tra H1, title, meta description, mục lục, CTA label, FAQ, schema, internal links và layout trên trình duyệt."),
            ("Bài này liên quan gì đến prompt ChatGPT cho Windsurf?", "Một prompt debug rõ từ ChatGPT giúp Windsurf sửa đúng source file thay vì vá sai output."),
        ],
    },
    "windsurf-to-codex-workflow": {
        "title": "Windsurf to Codex Workflow",
        "summary": "My practical workflow for using Windsurf to build the first version, then Codex to repair, validate, and clean up the project.",
        "vi_title": "Workflow từ Windsurf sang Codex",
        "vi_summary": "Workflow thực tế của tôi: dùng Windsurf dựng bản đầu, rồi dùng Codex để sửa, validate và cleanup dự án.",
        "eyebrow": "AI coding workflow | First build to repair | Last updated",
        "vi_eyebrow": "Workflow AI coding | Từ bản đầu đến sửa lỗi | Cập nhật",
        "h1": "My Windsurf to Codex Workflow for Real Project Cleanup",
        "vi_h1": "Workflow Windsurf sang Codex của tôi để cleanup dự án thật",
        "intro": [
            "I do not expect Windsurf to finish every project perfectly. I use it for speed. It creates the first version, makes the idea visible, and gives me something to test. Then I use Codex when the project needs focused repair.",
            "This is the workflow I use on real static sites, SEO systems, bilingual pages, and automation ideas. Windsurf gives me momentum. Codex helps me fix the parts that must be correct: routing, validation, schema, language, layout, and deployment cleanup.",
            "This article supports my main guide on ChatGPT prompts for Windsurf. The missing piece is what happens after Windsurf has created the first build and the project starts showing real problems.",
        ],
        "vi_intro": [
            "Tôi không kỳ vọng Windsurf hoàn thiện mọi dự án một cách hoàn hảo. Tôi dùng nó để lấy tốc độ. Nó tạo bản đầu, biến ý tưởng thành thứ nhìn thấy được và cho tôi thứ để test. Sau đó tôi dùng Codex khi dự án cần sửa tập trung.",
            "Đây là workflow tôi dùng với static site, hệ thống SEO, trang song ngữ và các ý tưởng automation thật. Windsurf tạo đà. Codex giúp tôi sửa những phần cần đúng: routing, validation, schema, ngôn ngữ, layout và cleanup triển khai.",
            "Bài này hỗ trợ bài chính về prompt ChatGPT cho Windsurf. Phần còn thiếu là chuyện xảy ra sau khi Windsurf đã tạo bản đầu và dự án bắt đầu lộ lỗi thật.",
        ],
        "sections": [
            {
                "id": "when-windsurf",
                "heading": "When I use Windsurf",
                "vi_heading": "Khi nào tôi dùng Windsurf",
                "paragraphs": [
                    "I use Windsurf when the project needs a visible first draft. That might be a new blog page, a dashboard section, a static route, a CTA block, or a layout update. At this stage, speed matters because I need something concrete to inspect.",
                    "Windsurf is useful when the task is broad but still structured. If I provide a clear prompt, it can create the initial files and connect the obvious pieces. It helps me move from planning into testing.",
                    "But I treat the output as a first build, not a final build. The first version may have duplicated logic, weak copy, missing internal links, incomplete SEO metadata, or small CSS problems that only appear on mobile.",
                ],
                "vi_paragraphs": [
                    "Tôi dùng Windsurf khi dự án cần một bản nháp đầu có thể nhìn thấy. Đó có thể là bài blog mới, section dashboard, static route, CTA block hoặc cập nhật layout. Ở giai đoạn này, tốc độ quan trọng vì tôi cần thứ cụ thể để kiểm tra.",
                    "Windsurf hữu ích khi task rộng nhưng vẫn có cấu trúc. Nếu prompt rõ, nó có thể tạo file ban đầu và nối các phần hiển nhiên. Nó giúp tôi chuyển từ lập kế hoạch sang test.",
                    "Nhưng tôi xem output là bản build đầu, không phải bản cuối. Bản đầu có thể có logic lặp, copy yếu, thiếu internal links, metadata SEO chưa đủ hoặc lỗi CSS nhỏ chỉ hiện trên mobile.",
                ],
            },
            {
                "id": "when-codex",
                "heading": "When I move the task to Codex",
                "vi_heading": "Khi nào tôi chuyển task sang Codex",
                "paragraphs": [
                    "I move to Codex when the problem becomes specific. If a route returns 404, if FAQ schema is duplicated, if the Vietnamese page is still English, or if code blocks overflow the article card, I do not want another broad first draft. I want a careful fix.",
                    "Codex works best when I give it the failing URL, the likely source files, the expected behavior, and the commands to run. It can inspect the codebase, patch source files, rebuild, and tell me what changed.",
                    "This division of labor keeps the project calmer. Windsurf does not need to be perfect. Codex does not need to invent the whole feature. Each tool has a job.",
                ],
                "vi_paragraphs": [
                    "Tôi chuyển sang Codex khi vấn đề đã cụ thể. Nếu route bị 404, FAQ schema bị lặp, trang tiếng Việt vẫn là tiếng Anh, hoặc code block tràn khỏi card bài viết, tôi không cần thêm một bản nháp rộng. Tôi cần một bản sửa cẩn thận.",
                    "Codex hoạt động tốt nhất khi tôi đưa URL lỗi, file nguồn có khả năng liên quan, hành vi mong muốn và lệnh cần chạy. Nó có thể inspect codebase, patch source, rebuild và báo thay đổi.",
                    "Cách chia việc này giúp project ổn hơn. Windsurf không cần hoàn hảo. Codex không cần phát minh toàn bộ tính năng. Mỗi công cụ có một vai trò.",
                ],
            },
            {
                "id": "handoff-notes",
                "heading": "What I collect before handing off to Codex",
                "vi_heading": "Tôi chuẩn bị gì trước khi giao cho Codex",
                "paragraphs": [
                    "Before I send the Codex prompt, I collect evidence. Screenshots show visual layout problems. Error messages show exactly what failed. File paths help narrow the search. A validation command gives Codex a clear finish line.",
                    "The best handoff notes usually include the user-facing problem, the expected behavior, the source files to inspect, what not to change, and the test commands. This turns a messy issue into a repair ticket.",
                    "For SEO pages, I also include sitemap, canonical, hreflang, FAQ schema, internal links, and `/go/` redirect behavior. Those details are easy to break during a broad cleanup.",
                ],
                "vi_paragraphs": [
                    "Trước khi gửi prompt cho Codex, tôi thu thập bằng chứng. Screenshot cho thấy lỗi layout. Error message cho biết chính xác phần fail. File path giúp thu hẹp phạm vi tìm kiếm. Lệnh validation cho Codex một điểm kết thúc rõ.",
                    "Ghi chú handoff tốt thường gồm vấn đề người dùng nhìn thấy, hành vi mong muốn, file nguồn cần kiểm tra, phần không được thay đổi và lệnh test. Như vậy một lỗi lộn xộn trở thành ticket sửa chữa rõ ràng.",
                    "Với trang SEO, tôi cũng nhắc sitemap, canonical, hreflang, FAQ schema, internal links và hành vi redirect `/go/`. Những chi tiết đó rất dễ bị phá khi cleanup quá rộng.",
                ],
            },
            {
                "id": "prompt-example-codex",
                "heading": "Prompt example: Codex repair prompt",
                "vi_heading": "Ví dụ prompt: prompt sửa lỗi cho Codex",
                "paragraphs": [
                    "This is the kind of prompt I use after Windsurf creates the first version and I find a concrete issue.",
                    "It is more focused than the Windsurf prompt because Codex is being asked to repair, not explore.",
                ],
                "vi_paragraphs": [
                    "Đây là kiểu prompt tôi dùng sau khi Windsurf tạo bản đầu và tôi tìm thấy một lỗi cụ thể.",
                    "Nó tập trung hơn prompt cho Windsurf vì Codex được yêu cầu sửa, không phải khám phá.",
                ],
                "code": "The first build is working locally, but the generated GitHub Pages output has a problem: /vi/blog/example-page/ still shows English article body. Inspect the article generator, Vietnamese localization module, generated site_output, and docs output. Fix the source pipeline so the Vietnamese page is natural Vietnamese while prompt/code blocks remain English. Do not change the English page. Rebuild, sync docs, run language integrity, validate links, and report exact files changed.",
            },
            {
                "id": "prompt-example-validation",
                "heading": "Prompt example: validation and deployment cleanup",
                "vi_heading": "Ví dụ prompt: validation và cleanup triển khai",
                "paragraphs": [
                    "When the issue is close to deployment, I make the prompt even stricter. The tool should not invent new features. It should verify the current pipeline.",
                    "This is useful before committing a fix to a GitHub Pages site.",
                ],
                "vi_paragraphs": [
                    "Khi lỗi gần giai đoạn deploy, tôi làm prompt chặt hơn nữa. Công cụ không nên phát minh tính năng mới. Nó nên kiểm tra pipeline hiện tại.",
                    "Prompt này hữu ích trước khi commit một bản sửa cho site GitHub Pages.",
                ],
                "code": "Run the local build and validation pipeline for this static site. Confirm sitemap includes the intended SEO pages, excludes /go/, has no broken internal links, has no placeholder text, and language integrity passes. Do not deploy. Do not call external APIs. If a generated docs page changed, explain whether it is required for GitHub Pages. Return exact git add commands and avoid git add .",
            },
            {
                "id": "mistakes",
                "heading": "Common mistakes in the handoff",
                "vi_heading": "Lỗi thường gặp khi chuyển việc",
                "paragraphs": [
                    "One mistake is handing Codex a vague complaint like \"the site is broken.\" That creates unnecessary exploration. A better prompt says which URL is broken, what you expected, and which validation failed.",
                    "Another mistake is asking Windsurf to keep fixing the same issue after the first build becomes tangled. If the problem needs source-level reasoning, I move it to Codex instead of generating more layers on top.",
                    "A third mistake is skipping the final browser check. Tests can pass while the UI still feels wrong. I still open the page and inspect the article, CTA, language switcher, and prompt blocks.",
                ],
                "vi_paragraphs": [
                    "Một lỗi là giao cho Codex một mô tả mơ hồ như \"site bị lỗi\". Cách đó khiến nó phải dò quá rộng. Prompt tốt hơn nêu URL lỗi, điều mong muốn và validation nào fail.",
                    "Lỗi khác là tiếp tục yêu cầu Windsurf sửa cùng một vấn đề sau khi bản đầu đã rối. Nếu lỗi cần suy luận ở source level, tôi chuyển sang Codex thay vì generate thêm lớp mới.",
                    "Lỗi thứ ba là bỏ qua kiểm tra bằng trình duyệt. Test có thể pass nhưng UI vẫn chưa ổn. Tôi vẫn mở trang và kiểm tra bài viết, CTA, language switcher và prompt block.",
                ],
            },
            {
                "id": "related-guides",
                "heading": "Related guides",
                "vi_heading": "Hướng dẫn liên quan",
                "paragraphs": [
                    "If you are starting before the first build, read the Windsurf prompt checklist. If you are writing prompts with ChatGPT first, read the main ChatGPT prompts for Windsurf article. If your issue is bilingual output, read the mixed-language guide.",
                    "Together, these guides describe the loop I use: ChatGPT for prompt clarity, Windsurf for first build speed, Codex for focused repair, and validation before publishing.",
                ],
                "vi_paragraphs": [
                    "Nếu bạn đang ở giai đoạn trước bản build đầu, hãy đọc checklist prompt Windsurf. Nếu bạn viết prompt bằng ChatGPT trước, đọc bài chính về prompt ChatGPT cho Windsurf. Nếu vấn đề là output song ngữ, đọc bài xử lý mixed-language.",
                    "Các bài này ghép lại thành vòng lặp tôi dùng: ChatGPT để làm rõ prompt, Windsurf để tạo bản đầu nhanh, Codex để sửa tập trung và validation trước khi publish.",
                ],
            },
        ],
        "faq": [
            ("Should I use Windsurf or Codex first?", "I use Windsurf first when I need a visible draft, then Codex when the problem becomes specific and needs careful repair."),
            ("What is Codex better at in this workflow?", "Codex is better for focused debugging, refactoring, validation fixes, SEO cleanup, routing issues, and production-readiness tasks."),
            ("Can Windsurf finish a full project alone?", "Sometimes it can get close, but I still test the result and use Codex when the project needs reliable cleanup."),
            ("What should I include in a Codex repair prompt?", "Include the failing URL, expected behavior, likely source files, constraints, validation commands, and what not to change."),
            ("How does this help beginners?", "It gives beginners a clear sequence: use Windsurf for momentum, test manually, then ask Codex to fix specific problems."),
        ],
        "vi_faq": [
            ("Nên dùng Windsurf hay Codex trước?", "Tôi dùng Windsurf trước khi cần bản nháp có thể nhìn thấy, rồi dùng Codex khi lỗi đã cụ thể và cần sửa cẩn thận."),
            ("Codex mạnh hơn ở đâu trong workflow này?", "Codex mạnh hơn với debugging tập trung, refactor, sửa validation, cleanup SEO, lỗi routing và các task production-readiness."),
            ("Windsurf có thể hoàn thiện cả dự án một mình không?", "Đôi khi nó có thể làm gần xong, nhưng tôi vẫn test kết quả và dùng Codex khi dự án cần cleanup đáng tin cậy."),
            ("Prompt sửa lỗi cho Codex nên có gì?", "Nên có URL lỗi, hành vi mong muốn, file nguồn có khả năng liên quan, ràng buộc, lệnh validation và phần không được thay đổi."),
            ("Workflow này giúp người mới thế nào?", "Nó cho người mới một trình tự rõ: dùng Windsurf để tạo đà, test thủ công, rồi nhờ Codex sửa vấn đề cụ thể."),
        ],
    },
}


SUPPORTING_BLOG_RELATED = [
    ("chatgpt-prompts-for-windsurf", "ChatGPT prompts for Windsurf", "prompt ChatGPT cho Windsurf"),
    ("windsurf-prompt-checklist", "Windsurf prompt checklist", "checklist prompt Windsurf"),
    ("fix-windsurf-mixed-language", "Fix Windsurf mixed language output", "sửa lỗi lẫn ngôn ngữ với Windsurf"),
    ("windsurf-to-codex-workflow", "Windsurf to Codex workflow", "workflow Windsurf sang Codex"),
]
