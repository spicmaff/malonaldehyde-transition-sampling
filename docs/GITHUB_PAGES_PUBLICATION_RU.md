# Публичная версия Proton / Potential

Основной адрес: **https://spicmaff.github.io/malonaldehyde-transition-sampling/**.
Исходники, исправления и [материалы приёмки](../reports/site-acceptance-81efe611/README.md)
находятся в этом репозитории. GitHub Pages публикуется штатным `research-site`
workflow из `main` после проверок. Фактические commit/tree доступны в
[build-identity.json](https://spicmaff.github.io/malonaldehyde-transition-sampling/build-identity.json),
хеши ресурсов — в [build-manifest.json](https://spicmaff.github.io/malonaldehyde-transition-sampling/build-manifest.json).

При первой публикации commit `1362278c` побайтная сверка выявила расхождение
метаданных сборки: `npm ci` создавал 4067 неотслеживаемых файлов в
`tools/site/node_modules`, поэтому CI честно обозначал рабочую копию как dirty.
50 из 53 runtime-ресурсов совпали; различались `build-identity.json`,
`build-manifest.json` и содержащий метку сборки HTML. Научные данные и
исполняемый frontend не расходились.

Исправление добавляет в `tools/site/.gitignore` только каталог переустанавливаемых
browser-test dependencies. Регрессионная проверка в
`tests/test_publication_identity.py` создаёт настоящий временный Git-репозиторий:
появление зависимостей сохраняет идентичность чистого исходника, а добавление
настоящего исходного файла и изменение tracked-файла по-прежнему обнаруживаются.
Это не ослабляет проверку исходников и не меняет научные расчёты. Причина,
исходные и исправленные хеши записаны в
`provenance/PAGES_PUBLICATION_IDENTITY_V001.json`; пять прежних слоёв provenance
сохранены без изменений.

Исторические отчёты в каталоге приёмки сохраняют статусы на момент их выпуска.
Новая публикация выполняется по последующему запросу владельца. Оба приватных
Sites-предпросмотра и их аудитория сохранены. Машинные свидетельства текущего
развёртывания и повторной побайтной сверки публикуются в
[ветке свидетельств](https://github.com/spicmaff/malonaldehyde-transition-sampling/tree/independent-review-evidence/publications).
Готовность сайта не снимает ограничений main4500, квалификации COV и
сходимости PBE/NEB, изложенных на самом сайте.
