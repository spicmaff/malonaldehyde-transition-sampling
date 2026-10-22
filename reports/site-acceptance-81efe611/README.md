# Независимая приёмка и публикация Proton / Potential

Основной публичный адрес проекта: **https://spicmaff.github.io/malonaldehyde-transition-sampling/**.
Исправления прошли независимую приёмку на commit `81efe61100d4913b9306f38616dde1720636d377`.
Код, первичные данные и все исправления входят в историю этого репозитория; этот каталог добавляет отчёты и машинные свидетельства, не меняя научные массивы или frontend.

Полный финальный отчёт: [Final_Acceptance_Malonaldehyde_RU.html.gz](Final_Acceptance_Malonaldehyde_RU.html.gz).
Предыдущий подробный аудит: [Independent_Review_Malonaldehyde_RU.html.gz](Independent_Review_Malonaldehyde_RU.html.gz).
Это обычные gzip-архивы автономных HTML: после распаковки отчёты открываются в браузере, включая встроенные иллюстрации и приложения.

```sh
gzip -dk Final_Acceptance_Malonaldehyde_RU.html.gz
gzip -dk Independent_Review_Malonaldehyde_RU.html.gz
sha256sum -c SHA256SUMS
```

В отчётах сохранены исторические статусы на момент их выпуска. В частности, упоминание ожидавшего установки пакетов `visual-story` больше не является текущим статусом: **все пять workflow commit 81efe611 завершились успешно**. См. [WORKFLOWS_COMPLETED.json](WORKFLOWS_COMPLETED.json) и [REPRODUCTION_JOBS_COMPLETED.json](REPRODUCTION_JOBS_COMPLETED.json).

Проверено 197 Python-тестов, 35 JavaScript-тестов, 120 комбинаций маршрута/ширины/темы и 150 научных панелей. Все 53 опубликованных runtime-ресурса исправленного Sites-предпросмотра совпали с проверенной сборкой. Первичные входы и численные результаты независимого verifier сохранены в [INDEPENDENT_SCIENCE.json](INDEPENDENT_SCIENCE.json); соответствие историческим данным — в [SCIENCE_CONTINUITY.json](SCIENCE_CONTINUITY.json).

Настоящий этап переносит проверенную версию в основную ветку для штатной публикации GitHub Pages по новому запросу владельца. Приватность обоих Sites-предпросмотров остаётся прежней. Публикуется статический сайт на основе уже публичных материалов; токены, cookies, пароли и отсутствующие приватные архивы в репозиторий не включены.

Фактический commit публичной сборки можно проверить по [build-identity.json](https://spicmaff.github.io/malonaldehyde-transition-sampling/build-identity.json), хеши ресурсов — по [build-manifest.json](https://spicmaff.github.io/malonaldehyde-transition-sampling/build-manifest.json). Развёртывание выполняется существующим [research-site workflow](../../.github/workflows/research-site.yml) после успешных проверок; его окончательный статус следует проверять в Actions, а не выводить из наличия этого документа.

В текстовых копиях CI-журналов пути домашнего каталога публичного runner нормализованы в `/home/USER/` согласно существующему аудиту репозитория. Исходные и экспортные хеши сохранены в [PUBLIC_EXPORT.json](PUBLIC_EXPORT.json); статусы и научные числа не менялись. Публикуются редакционные копии HTML: адреса прежних приватных предпросмотров и служебные пути опущены, ссылка на текущий сайт обновлена. Научные результаты и исторические статусы сохранены. Исходные байты доступны в истории репозитория до этой редакции; исходные и экспортные хеши перечислены в `PUBLIC_EXPORT.json`.

Полные PNG всех состояний находятся в [ветке независимых свидетельств](https://github.com/spicmaff/malonaldehyde-transition-sampling/tree/independent-review-evidence/81efe61100d4913b9306f38616dde1720636d377).

Готовность сайта не означает полной физической валидации. Полный main4500 остаётся недоступным; экспорт, native parity и внешняя квалификация COV не выполнены; исследования численной сходимости PBE/NEB отсутствуют. Эти ограничения и конкретные дальнейшие исследования приведены в отчётах и на сайте.
