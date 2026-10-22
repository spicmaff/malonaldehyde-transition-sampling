# Публикация проверенного Proton / Potential

Рабочий публичный адрес: **https://spicmaff.github.io/malonaldehyde-transition-sampling/**.
Опубликован commit `8df2c82d87c9fe2c4884d496fdaa46d3587c2f16` из `main`, tree `05523a265aff542977c74baeb9aaf1bad6ac7612`.

[Публикация GitHub Pages](https://github.com/spicmaff/malonaldehyde-transition-sampling/actions/runs/39864195677) завершилась успешно. Независимое чтение обычного адреса и всех 53 runtime-ресурсов побайтно совпало с чистой локальной сборкой. `build-identity.json` сообщает `working_copy_clean=true`, untracked count 0; 31 MIME-проверка JS/CSS/JSON прошла. Файлы `PUBLICATION.json`, `PUBLISHED_RESOURCE_PARITY.json`, `CANONICAL_URL.json` и `DEPLOYMENTS_FIXED.json` содержат проверяемые подтверждения.

В первом опубликованном commit `1362278c` метаданные обнаружили 4067 установленных, но не игнорируемых browser-test dependencies. 50 из 53 ресурсов совпали; различались метка сборки, manifest и содержащий метку HTML. Диагноз и первоначальное состояние сохранены в файлах FIRST и IDENTITY_FIRST_DIAGNOSIS.json. Новый `tools/site/.gitignore` исключает только переустанавливаемые npm dependencies; корневой .gitignore, прежние зарегистрированные исходники и пять прежних слоёв provenance сохранены. Регрессионный тест проверяет, что реальные изменения исходников по-прежнему обнаруживаются.

На финальном commit прошли 198 Python-тестов, проверка целостности, source/aggregate verifier и CI публикации с браузерными сценариями. Численные разделы и SHA-256 всех 130 первичных входов совпали с принятой версией 81efe611. Frontend-модули и научные массивы после неё не менялись; исследовательские ограничения main4500, COV и PBE/NEB остаются в силе. Новых физических запусков не было.

На момент сохранения снимка вспомогательный job visual-story на этом commit ещё ожидал установки системных пакетов; integrity и reproduction-smoke уже прошли. Его скрипты и данные не менялись и ранее прошли на 1362278c. Это не новый неуспешный тест и не условие штатного Pages deploy. Фактические статусы, без объявления всего CI зелёным, сохранены в WORKFLOWS_FIXED.json и REPRODUCTION_JOBS_FIXED.json.

Оба Sites-предпросмотра остались приватными, их версии и аудитория не изменялись. Исторические отчёты и сравнения находятся в [основной ветке](https://github.com/spicmaff/malonaldehyde-transition-sampling/tree/main/reports/site-acceptance-81efe611). Эти свидетельства дополняют их последующим публичным развёртыванием.

Для повторения live-сверки используется verify_public_pages.py с аргументами: каталог идентифицированной сборки, путь JSON-отчёта и публичный URL. Авторизация для GitHub Pages не передаётся. CI-журналы нормализуют только пути /home/USER/; статусы и научные числа сохранены.

The current public copy of `SITES_UNCHANGED.json` omits the former private preview URLs. Its identifiers, versions, access settings and statuses are unchanged. The original snapshot is preserved in the history at `3b676c406a8f71a11c997d166d3aa071266cd9f6`.
