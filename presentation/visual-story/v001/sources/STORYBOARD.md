# Storyboard v001

Вопрос: куда разместить одинаковое небольшое число дорогих DFT-конфигураций?

| Ролик / сцена | Вопрос и действие | Источник | Подпись и длительность | Переход / предел |
|---|---|---|---|---|
| A, 0–4 s | Молекула и два конца пути; удержание первого минимума | neb9.xyz, energy_profiles.tsv | Что меняется, когда протон переходит? | Спокойная камера; время не физическое |
| A, 4–28 s | H* перемещается между O; qPT и маркер энергии синхронны | 9 frozen PBE samples | Опорные точки и линии различимы | Cartesian presentation interpolation после Kabsch; без inference |
| A, 28–34 s | Второй минимум, удержание итогового состояния | Те же samples | Два минимума, между ними барьер | 36.072 meV относительно нижнего endpoint |
| B, 0–10 s | Два схематических размещения по 24 точки | docs/METHODS.md, v028 records | common36 + 24; L12; pool24/K24 | Схема, не координаты training geometries |
| B, 10–24 s | Две primary metrics; 9 images и endpoint overlap | science_status.json, saved v029 payload | Исходная locked-пара точнее; 2 ends в common36 | Не whole-independent NEB9/Audit21 |
| B, 24–38 s | Все 5 paired seeds на двух шкалах | seed_metrics.tsv | wins 4/5 barrier, 3/5 force | Соединяются пары, не scientific interpolation |
| B, 38–46 s | Удержание результата и процедурной оговорки | seed repair closure | 3/5 по обеим; SEED_SENSITIVE | Historic interleaving не стирается |
| C, 0–14 s | Полный Replay228 и увеличенный диапазон около stop | replay228_gamma.tsv, science_status.json | Crossings 143–147 | Индексы не время; γ не error |
| C, 14–27 s | Все 11 сохранённых force RMSE и A2 | validation11_force.tsv, serialization_guard.json | 11/11 raw ниже A2; overlap и guard FAIL | Не independent holdout; не overall PASS |
| C, 27–40 s | Простой terminal screen | final science status | STATIC_APPLICABILITY_FAIL; Gate1 не запущен | Не установлен force-accuracy failure; Blind12 закрыт |
| Teaser, 20 s | Вопрос → исходная пара → отрицательное продолжение | Те же sources | Краткий вход в историю | Сцены не приписывают одному model ID чужие результаты |
| Vertical, 22 s | Самостоятельная композиция молекулы и PBE curve | Те же 9 samples | Один протон, два минимума | 1080×1920, никакого обрезания horizontal frame |

Паузы в B/C намеренные: для чтения графиков и границ вывода. Плавность движения A/vertical обеспечивается 60 новыми положениями камеры/геометрии в секунду. B/C используют мягкие crossfades и читательские маркеры; статические графики не выдаются за динамический эксперимент. Звуковая дорожка отсутствует. Длительности выбраны по объёму объяснения, не по числу Stage IDs.
