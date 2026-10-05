#!/usr/bin/env python3
"""Build the portable editorial story, captions and reproducible presentation sources."""
from pathlib import Path
import argparse, csv, html, json, re, shutil, hashlib
import render_visual_story as rv

def write_tsv(path, rows, fields):
    with path.open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields,delimiter='\t',lineterminator='\n');w.writeheader();w.writerows(rows)

def sections(text):
    return {m.group(1):m.group(2).strip() for m in re.finditer(r'^## (.*?)\n(.*?)(?=^## |\Z)',text,re.M|re.S)}

def paragraph_html(s):
    s=html.escape(s)
    s=re.sub(r'`(.*?)`',r'<code>\1</code>',s)
    s=re.sub(r'\*\*(.*?)\*\*',r'<strong>\1</strong>',s)
    s=re.sub(r'(https://github\.com/[^\s<]+)',r'<a href="\1">\1</a>',s)
    return '<p>'+s.replace('\n',' ')+'</p>'

STORYBOARD='''# Storyboard v001

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
'''

VISUAL_SYSTEM='''# Visual system v001

Фон #11171e; основной текст #edf0eb; вторичный #9caab4; линии #34434f.
Basin всегда #e5ae65; targeted всегда #65d2c7. Отказ #f58089. O #d6a8a1, C #78919f, H #dde2df, переносимый H* #f2d892: химические цвета имеют отдельную роль от стратегии sampling.

Ролики: DejaVu Sans / Bold, 66 px заголовок с ограничением ширины 1748 px; 30–43 px смысловые подписи; 22–29 px источники и необходимые caveats. RGB→H.264 yuv420p, 1920×1080 либо 1080×1920, 60 fps, faststart. Шрифт не включён бинарно: требуется DejaVu Sans (Bitstream Vera / DejaVu license), ссылка и лицензия в THIRD_PARTY_NOTICES.md.

Молекулярная сцена: spheres с Lambert-like shading и specular highlight, свет слева сверху. 7 backbone/C–H connections иллюстративны; пунктир O···H* обозначает направляющие расстояния. Atom identity неизменна. Kabsch fit: O0 C2 C4 C6 O7. Камера качается медленно в узком диапазоне; значения qPT и R(O···O) считаются в 3D, без display rotation.

Графики: все frozen sample points видны; соединения NEB — presentation interpolation, paired-seed lines — связь пары. γ inset явно увеличен около stop. Никаких искусственных осей времени или новых intermediate predictions.

Витрина: editorial typography, одна строка навигации, широкий hero и узкая колонка чтения. Светлая читательская область согласуется с тёмной сценой. Нативные video controls и Restart, без autoplay. Mobile имеет вертикальный fallback и внешние читаемые captions. Reduced motion отключает scroll animation; медиа запускает сам читатель. Зависимости: стандартные browser APIs, локальные assets; без CDN, login, API.
'''

CSS='''
:root{--bg:#11171e;--ink:#edf0eb;--muted:#a2b0b9;--basin:#e5ae65;--targeted:#65d2c7;--fail:#f58089;--paper:#f2f3ee;--text:#17222a}
*{box-sizing:border-box}html{scroll-behavior:smooth;scroll-padding-top:95px}body{margin:0;font-family:system-ui,-apple-system,"Segoe UI",sans-serif;background:var(--paper);color:var(--text)}a{color:inherit;text-underline-offset:4px}button{font:inherit;cursor:pointer}nav{position:sticky;top:0;z-index:4;background:var(--bg);color:var(--ink);display:flex;align-items:center;justify-content:space-between;padding:18px 5vw;border-bottom:1px solid #33414c}nav .brand{font-size:14px;letter-spacing:.13em;text-decoration:none}nav .links{display:flex;gap:22px;font-size:14px}nav .links a{text-decoration:none}header{background:var(--bg);color:var(--ink);padding:65px 5vw 60px}.hero{max-width:1450px;margin:auto;display:grid;grid-template-columns:1.05fr 1fr;align-items:center;gap:35px}.eyebrow{letter-spacing:.16em;font-size:13px;text-transform:uppercase;color:var(--muted)}h1{font-size:clamp(48px,6vw,94px);line-height:1.01;letter-spacing:-.065em;font-weight:650;margin:28px 0}h1 em{font-style:normal;color:var(--targeted)}.lead{font-size:21px;line-height:1.6;max-width:560px;color:var(--muted)}.hero img{width:100%;height:auto}.hero-note{color:var(--muted);font-size:13px;line-height:1.6}.primary-link{display:inline-block;margin:18px 0;padding:13px 23px;border:1px solid var(--targeted);border-radius:4px;text-decoration:none;color:var(--targeted)}.deck{max-width:1300px;margin:50px auto 0;display:flex;gap:50px;border-top:1px solid #33414c;padding-top:27px}.deck strong{font-size:31px;color:var(--ink);display:block}.deck span{font-size:14px;color:var(--muted)}main{padding:65px 5vw 35px}.chapter{max-width:1250px;margin:0 auto 95px}.chapter-title{display:grid;grid-template-columns:100px 1fr;align-items:start;gap:30px;margin-bottom:28px}.chapter-num{font-size:19px;letter-spacing:.12em;color:#667a86;margin-top:10px}.chapter h2{font-size:clamp(33px,4vw,58px);font-weight:600;line-height:1.12;letter-spacing:-.045em;margin:0;max-width:970px}.prose{max-width:800px;margin-left:130px;font-size:20px;line-height:1.76}.prose p{margin:0 0 24px}.prose code{font-size:.86em;overflow-wrap:anywhere}figure{margin:38px 0 34px;background:var(--bg);color:var(--ink);border-radius:7px;overflow:hidden}video{display:block;width:100%;height:auto;background:var(--bg)}figcaption{padding:19px 26px;font-size:15px;line-height:1.65;color:var(--muted)}.video-actions{display:flex;align-items:center;gap:18px;padding:0 26px 23px}.video-actions button{background:transparent;border:1px solid #6f818b;border-radius:4px;padding:9px 17px;color:var(--ink)}.video-actions a{font-size:14px;color:var(--muted)}.mobile-video{display:none}.metric-block{margin:40px 0 35px 130px;border-top:1px solid #aebbc0;border-bottom:1px solid #aebbc0;padding:28px 0}.metric-row{display:grid;grid-template-columns:1.4fr 1fr 1fr;gap:22px;align-items:center;padding:12px 0}.metric-label{font-size:18px}.metric-value{font-size:38px;letter-spacing:-.04em;font-variant-numeric:tabular-nums}.metric-value small{display:block;font-size:13px;letter-spacing:0;color:#536b77}.b{color:#996123}.t{color:#186d64}.seed-panel{margin:40px 0 35px 130px;display:grid;grid-template-columns:1fr 1fr;gap:45px}.seed-panel h3{font-size:21px;font-weight:550;margin:0 0 15px}.seed-panel svg{display:block;width:100%;height:auto}.seed-panel p{font-size:15px;line-height:1.6}.aside-note{border-left:3px solid #1f8076;padding:7px 0 7px 23px;font-size:20px;line-height:1.65;margin:30px 0 30px 130px;max-width:800px}.negative{border-color:#bb5665}.sources{background:#e6eae5;padding:45px 5vw}.sources-inner{max-width:990px;margin:auto;font-size:17px;line-height:1.8}.sources h2{font-size:34px;letter-spacing:-.03em}.sources ul{padding-left:25px}.sources a,.prose a{overflow-wrap:anywhere}.footer{background:var(--bg);color:var(--muted);padding:30px 5vw;font-size:13px;line-height:1.7}.footer-inner{max-width:1250px;margin:auto;display:flex;justify-content:space-between;gap:25px}details{margin:25px 0}summary{cursor:pointer;font-weight:550}.teaser-block{max-width:1000px;margin:55px auto 0}.download-row{display:flex;gap:18px;flex-wrap:wrap}
@media(max-width:800px){nav{padding:15px 22px;gap:10px}nav .links{gap:12px;font-size:12px}nav .brand{font-size:10px;max-width:132px}header{padding:35px 24px 40px}.hero{grid-template-columns:minmax(0,1fr);gap:12px}.hero>*{min-width:0}h1{font-size:clamp(39px,10.4vw,61px);margin:22px 0;max-width:100%}.lead{font-size:19px}.hero img{max-width:100%;max-height:380px;object-fit:contain}.deck{gap:28px;flex-wrap:wrap;margin-top:30px}.deck strong{font-size:26px}.deck span{font-size:13px}main{padding:46px 23px 10px}.chapter{margin-bottom:65px}.chapter-title{grid-template-columns:minmax(0,1fr);gap:10px}.chapter-num{font-size:14px;margin:0}.chapter h2{font-size:37px;max-width:100%;overflow-wrap:break-word}.prose{margin-left:0;font-size:19px;line-height:1.74}.metric-block,.seed-panel,.aside-note{margin-left:0}.metric-row{grid-template-columns:minmax(0,1.2fr) minmax(0,1fr) minmax(0,1fr);gap:9px}.metric-label{font-size:14px;overflow-wrap:break-word}.metric-value{font-size:clamp(22px,6.4vw,29px)}.metric-value small{font-size:11px}.seed-panel{grid-template-columns:minmax(0,1fr);gap:20px}.aside-note{font-size:18px}.video-actions{padding:0 18px 18px;gap:16px}figcaption{padding:15px 18px;font-size:14px}.mobile-video{display:block}.mobile-video video{max-height:78vh;object-fit:contain}.sources{padding:35px 23px}.sources-inner{font-size:16px}.footer{padding:25px 23px}.footer-inner{display:block}.desktop-note{display:none}}
@media(prefers-reduced-motion:reduce){html{scroll-behavior:auto}*,*::before,*::after{animation:none!important;transition:none!important}}
'''

def seed_svg(data,key,limit):
    rows=[]
    for tick in (0,limit/2,limit):
        x=65+tick/limit*365;rows.append(f'<line x1="{x}" x2="{x}" y1="20" y2="272" stroke="#ccd6d6"/>')
        rows.append(f'<text x="{x}" y="310" text-anchor="middle">{tick:g}</text>')
    for seed in range(5):
        pair={r['branch']:float(r[key]) for r in data.seeds if int(r['seed_index'])==seed}; y=45+seed*49
        a=65+pair['basin']/limit*365;b=65+pair['targeted']/limit*365
        rows.extend([f'<text x="20" y="{y+6}">{seed+1}</text>',f'<line x1="{a}" x2="{b}" y1="{y}" y2="{y}" stroke="#78909a" stroke-width="2"/>',f'<circle cx="{a}" cy="{y}" r="7" fill="#ac732f"/>',f'<circle cx="{b}" cy="{y}" r="7" fill="#18766c"/>'])
    return '<svg viewBox="0 0 490 325" role="img" aria-label="Все пять paired seeds; меньше ошибка — точнее" style="font:20px system-ui;fill:#425965">'+''.join(rows)+'</svg>'

def media_video(name,caption,ident,mobile=False):
    stem=Path(name).stem
    return f'''<figure class="{'mobile-video' if mobile else ''}"><video id="{ident}" controls playsinline preload="metadata" poster="media/{stem}_poster.jpg"><source src="media/{name}" type="video/mp4">Ваш браузер не поддерживает MP4. <a href="media/{name}">Открыть видео</a>.</video><figcaption>{caption}</figcaption><div class="video-actions"><button type="button" data-restart="{ident}">Сначала</button><a href="media/{name}" download>Скачать MP4</a></div></figure>'''

def build(args):
    out=args.out;out.mkdir(parents=True,exist_ok=True)
    for name in ('media','text','sources','QA','assets'):(out/name).mkdir(exist_ok=True)
    data=rv.Data(args.data);old=(args.baseline/'TG_LONGREAD_FULL.md').read_text();ss=sections(old)
    intro='''# Куда поставить 24 DFT-точки?

Малональдегид — маленькая молекула с большим для машинного потенциала вопросом. Один протон может перейти от одного атома кислорода к другому. По краям пути находятся устойчивые состояния, а между ними — переходная область, которую модель тоже должна описать. Где взять обучающие примеры для этого перехода, если дорогих DFT-расчётов можно сделать лишь немного?

Я сравнил два способа разместить одинаковое число конфигураций. Один дополнял обучение около минимумов, другой — ближе к переносу протона. У исходной сохранённой пары второй способ дал гораздо меньшие ошибки барьера и сил. Затем оказалось, что этот успех зависит от случайной инициализации, а хорошая статическая таблица ещё не означает готовности к свободной динамике.

Эта история проходит весь путь: от молекулы и бюджета данных до удачного статического сравнения, проверки его ограничений и честной остановки поздней модели. Новое оформление использует сохранённые геометрии и числа. Научные модели, критерии и результаты остаются прежними.
'''
    chapters=[
      ('Один протон, два минимума','''На рисунке и в первом ролике показаны девять сохранённых геометрий PBE NEB-пути. Я отмечаю переносимый атом как H*. Координата qPT — разность расстояний от него до левого и правого кислорода: d(H*, O слева) − d(H*, O справа). На левом конце она отрицательна, на правом положительна. Около центра протон находится между двумя атомами кислорода.

График рядом с молекулой связывает геометрию с относительной энергией. Девять точек — сохранённые вычислительные опоры. Максимум относительно более низкого endpoint составляет 36,072 meV. Это внутренний PBE-ориентир для дальнейшего сравнения моделей.

Между этими точками анимация показывает плавную визуальную интерполяцию после совмещения молекулярного остова. Это монтажное представление замороженного NEB-пути: секунды ролика не являются физическим временем реакции, промежуточные положения не размечались заново, а движение не является валидированной MD-траекторией. Соединительные линии на энергетическом графике имеют ту же презентационную роль.'''),
      ('Одинаковые 60 конфигураций, разное размещение',ss['Что сравнивалось']),
      ('Сильный результат исходной пары',ss['Что показала исходная сохранённая пара']),
      ('Что именно было независимо',ss['Где заканчивается независимость проверки']),
      ('Пять seeds меняют силу вывода',ss['Почему появился отдельный аудит случайности']),
      ('Точность на пути и применимость при движении',ss['Почему статической точности оказалось недостаточно']+'\n\n'+ss['Что добавила transition-tube ветка']),
      ('Почему Train119 остановился',ss['Чем закончилась ветка Train119']),
      ('Что остаётся проверяемым',ss['Что теперь можно проверить самому'])
    ]
    # Keep the provenance appendix short in the reading flow.
    ledger='''Финальная версия реестра V005 также исправила ошибку самого аудитора: поиск подстроки FAIL внутри FAILURE принимал успешные review технического сбоя за новые scientific FAIL. Исправлены семь классов и 21 source binding; собственный статус стадии отделён от научного исхода, который она сохраняет. Все настоящие научные отказы остаются отрицательными. Это исправление учёта, а не улучшение потенциала. Подробная таблица истории доступна в источниках.'''
    chapters[-1]=(chapters[-1][0],ledger+'\n\n'+chapters[-1][1])
    # The old conclusion referred to the prior corrective release; presentation URLs are explicit.
    chapters[-1]=(chapters[-1][0],chapters[-1][1].split('Репозиторий:')[0].strip()+'''\n\nИсходная научная граница закреплена релизом v1.1.2. Новая визуальная версия v1.2.0 добавляет рассказ, анимации и локальную витрину; она не объявляет новый научный результат. Компактные данные и rendering source позволяют проверить числа и заново собрать это представление без доступа к приватному 80-GB дереву.''')
    full=intro+'\n\n'+'\n\n'.join('## '+title+'\n\n'+body for title,body in chapters)+'\n\nРепозиторий: https://github.com/spicmaff/malonaldehyde-transition-sampling\n'
    assert 12000<=len(full)<=20000, len(full)
    compact=(args.baseline/'TG_LONGREAD_COMPACT.md').read_text()
    compact=compact.replace('# Куда поставить одинаковый DFT-бюджет: опыт с переносом протона и MTP','# Куда поставить 24 DFT-точки? Перенос протона и пределы машинного потенциала')
    compact=compact.replace('Для трёх видео дополнительно нужен ffmpeg.','Для прежних и новых роликов дополнительно нужен ffmpeg.')
    compact=compact.replace('Релиз: https://github.com/spicmaff/malonaldehyde-transition-sampling/releases/tag/v1.1.2',
      'Научная граница: https://github.com/spicmaff/malonaldehyde-transition-sampling/releases/tag/v1.1.2\n\nВизуальная версия: https://github.com/spicmaff/malonaldehyde-transition-sampling/releases/tag/v1.2.0')
    compact+='\n\nАнимация молекулы — интерполированная визуализация замороженного NEB-пути. Время воспроизведения не физическое время; новых DFT-меток, inference или динамики для оформления не выполнялось.\n'
    assert 5000<=len(compact)<=8000,len(compact)
    (out/'text/LONGREAD_FULL.md').write_text(full)
    (out/'text/LONGREAD_COMPACT.md').write_text(compact)
    telegram=compact+'''\n\n---\nПорядок медиа для ручной публикации:\n\n1. 04_story_teaser.mp4 — вопрос, исходная пара и граница продолжения.\n2. 01_proton_path.mp4 — 9 опорных PBE геометрий; display interpolation, не физическое время.\n3. 02_equal_budget.mp4 — 60 = 36 + 24, original metrics и все пять paired seeds.\n4. 03_applicability_boundary.mp4 — Train119, Replay228 и raw Validation11; terminal FAIL.\n5. 05_proton_vertical.mp4 — отдельная вертикальная композиция для телефона.\n\nТекст переносится вручную несколькими сообщениями при необходимости. Ничего не отправлено автоматически.\n'''
    (out/'text/TELEGRAM_READY.md').write_text(telegram)
    placements=[
      {'episode':'01 / molecular path','file':'media/01_proton_path.mp4','caption':'9 сохранённых PBE NEB images. Плавное движение — display interpolation, время не физическое.','alt':'Молекула с выделенным H* и синхронным указателем на энергетическом профиле.','source':'sources/inputs/neb9.xyz; energy_profiles.tsv'},
      {'episode':'02–05 / budget, original metrics, seeds','file':'media/02_equal_budget.mp4','caption':'Одинаковый бюджет common36+24. Исходная locked-пара, overlap и все пять seeds.','alt':'Две схемы sampling, ошибки барьера/сил и пять пар точек.','source':'sources/inputs/science_status.json; seed_metrics.tsv'},
      {'episode':'07 / Train119 closure','file':'media/03_applicability_boundary.mp4','caption':'Пять crossings 143–147. Raw силы ниже A2, но independence и serialization caveats сохраняются.','alt':'Полный γ replay, увеличенный диапазон, 11 force RMSE и terminal FAIL.','source':'sources/inputs/replay228_gamma.tsv; validation11_force.tsv; serialization_guard.json'},
      {'episode':'hero / short introduction','file':'media/04_story_teaser.mp4','caption':'Краткий вопрос, исходное статическое сравнение и отдельный итог поздней модели.','alt':'Три сцены визуальной истории.','source':'sources/MEDIA_SOURCE_MANIFEST.tsv'},
      {'episode':'01 / phone fallback','file':'media/05_proton_vertical.mp4','caption':'Самостоятельный вертикальный layout; NEB presentation interpolation.','alt':'Молекула над графиком PBE с крупной координатой qPT.','source':'sources/inputs/neb9.xyz; energy_profiles.tsv'}]
    write_tsv(out/'text/MEDIA_PLACEMENT.tsv',placements,list(placements[0]))
    (out/'text/CAPTIONS_RU.md').write_text('# Подписи к медиа\n\n'+'\n\n'.join('## '+r['file']+'\n\n'+r['caption'] for r in placements)+'\n')
    (out/'sources/STORYBOARD.md').write_text(STORYBOARD)
    (out/'sources/VISUAL_SYSTEM.md').write_text(VISUAL_SYSTEM)
    # Preserve exact authority hashes, with the owner root replaced by a public placeholder.
    fact=rv.table(args.baseline/'TG_POST_FACTCHECK.tsv')
    for row in fact:
        for k,v in row.items():row[k]=re.sub(r'/home/[^/]+/malonaldehyde_mtp_al/','${PROJECT_ROOT}/',v)
        row['review_status']='PASS_PRESENTATION_SCOPE_REVIEW'
    extra=[('V01','9 atom geometries; qPT and 36.072 meV PBE profile','neb9.xyz;energy_profiles.tsv','Coordinates interpolated only for display','NEB visualization; seconds not physical time','Validated free MD'),
      ('V02','Replay228 plot and numerical magnification','replay228_gamma.tsv','Development benchmark, no physical time axis','Five crossings at143–147; gamma diagnostic','Large force errors at these crossings'),
      ('V03','All 11 saved force errors and formal guard failure','validation11_force.tsv;serialization_guard.json','Not independent holdout','Raw 11/11 below A2 with guard FAIL','Independent overall PASS'),
      ('V04','All five paired seeds displayed','seed_metrics.tsv','No best-seed selection','4/5 barrier;3/5 force;3/5 both; SEED_SENSITIVE','Seed-robust universal improvement')]
    for ident,claim,names,caveat,allow,forbid in extra:
        hashes=';'.join(n+':'+hashlib.sha256((args.data/n).read_bytes()).hexdigest() for n in names.split(';'))
        fact.append(dict(zip(fact[0],(ident,claim,'sources/inputs/'+names,hashes,'saved data',caveat,allow,forbid,'PASS_PRESENTATION_SCOPE_REVIEW'))))
    write_tsv(out/'sources/CLAIM_FACTCHECK.tsv',fact,list(fact[0]))
    shutil.copytree(args.data,out/'sources/inputs',dirs_exist_ok=True)
    shutil.copy2(Path(__file__).with_name('render_visual_story.py'),out/'sources/render_visual_story.py')
    (out/'sources/RENDERING.md').write_text('''# Reproduce the visual presentation

Requires Python 3.11+, numpy, Pillow, ffmpeg (libx264), and system DejaVu Sans fonts. No MLIP, QE, selector, training or dynamics calls. From this package root:

```bash
python sources/render_visual_story.py --data sources/inputs --out rerendered --kind all
```

For the repository use `python scripts/visual_story/render_visual_story.py --data data/visual_story/v001 --out render-output/visual-story --kind all`. `--validate-only` checks saved scientific inputs and 2001 display-interpolation samples; `--proof` renders a four-second excerpt and review frames.

Frames stream directly to ffmpeg, without a frame-directory storage requirement. All charts use compact saved values. Renderer parameters and display interpolation are described in VISUAL_SYSTEM.md / STORYBOARD.md. Static pauses are intended for reading; changing NEB/camera frames are genuinely sampled at 60 fps.
''')
    (out/'sources/THIRD_PARTY_NOTICES.md').write_text('''# Third-party notices

Rendering code follows the repository MIT license. Compact saved project data retain their existing public provenance. No MLIP executable, UPF, QE output binary, private development history or Blind12 payload is included.

NumPy: BSD 3-Clause; Pillow: HPND. ffmpeg is an external encoder, not bundled; the invoked libx264 build is GPL-compatible and must be installed separately. DejaVu Sans is used via system fonts, not distributed as a font binary. Its upstream license is the Bitstream Vera license with DejaVu additions in the public domain: https://dejavu-fonts.github.io/License.html . HTML uses system fonts, no external dependency or CDN.
''')
    im=rv.Image.new('RGB',(1400,1100),rv.BG);rv.molecule(im,data,.22,9,700,620,205)
    im.save(out/'assets/hero_molecule.jpg',quality=93)
    (out/'assets/style.css').write_text(CSS)
    (out/'assets/story.js').write_text('''document.querySelectorAll('[data-restart]').forEach(b=>b.addEventListener('click',()=>{const v=document.getElementById(b.dataset.restart);v.currentTime=0;v.play().catch(()=>{});}));
// Videos have native play/pause controls. No autoplay, sound or network access.
''')
    content=[]
    for i,(title,body) in enumerate(chapters,1):
        section=f'<section class="chapter" id="chapter-{i}"><div class="chapter-title"><span class="chapter-num">{i:02d} / ИСТОРИЯ</span><h2>{html.escape(title)}</h2></div>'
        paragraphs=body.split('\n\n')
        section+='<div class="prose">'+''.join(paragraph_html(p) for p in paragraphs)+'</div>'
        if i==1:
            section+=media_video('01_proton_path.mp4',placements[0]['caption'],'path')
            section+=media_video('05_proton_vertical.mp4',placements[4]['caption'],'vertical',True)
        if i==3:
            section+='''<div class="metric-block"><div class="metric-row"><div class="metric-label">Исходная locked-пара</div><div class="metric-value b" style="font-size:24px">basin</div><div class="metric-value t" style="font-size:24px">targeted</div></div><div class="metric-row"><div class="metric-label">Ошибка барьера</div><div class="metric-value b">35,2457<small>meV</small></div><div class="metric-value t">4,1004<small>meV</small></div></div><div class="metric-row"><div class="metric-label">Transition force RMSE</div><div class="metric-value b">0,176083<small>eV/Å</small></div><div class="metric-value t">0,078685<small>eV/Å</small></div></div></div>'''
        if i==2:
            section+=media_video('02_equal_budget.mp4',placements[1]['caption'],'budget')
        if i==5:
            section+='<div class="seed-panel"><div><h3>Ошибка барьера, meV</h3>'+seed_svg(data,'lower_endpoint_barrier_abs_error_meV',35)+'<p>targeted лучше в 4/5 пар.</p></div><div><h3>Transition force RMSE, eV/Å</h3>'+seed_svg(data,'transition_region_force_component_RMSE_eV_A',.24)+'<p>targeted лучше в 3/5 пар. По обеим метрикам — 3/5.</p></div></div><div class="aside-note">Все пять pairs показаны. Итог — SEED_SENSITIVE.</div>'
        if i==7:
            section+=media_video('03_applicability_boundary.mp4',placements[2]['caption'],'boundary')
            section+='<div class="aside-note negative">Остановка по применимости сохранена. Провал точности сил Train119 не установлен; готовность к реактивной динамике не доказана.</div>'
        content.append(section+'</section>')
    hero='''<header><div class="hero"><div><div class="eyebrow">DFT · MTP · перенос протона</div><h1>Куда поставить<br><em>24 DFT-точки?</em></h1><p class="lead">Одинаковый бюджет, два способа разместить данные. Статический успех — и проверка, которая не позволила объявить модель готовой к динамике.</p><a class="primary-link" href="#chapter-1">Начать историю ↓</a></div><div><img src="assets/hero_molecule.jpg" alt="Малональдегид: выделенный переносимый протон между двумя кислородами" width="1400" height="1100"><p class="hero-note">Сохранённая PBE NEB-геометрия с визуальной интерполяцией. <br>Научная граница v1.1.2 · визуальная версия v1.2.0.</p></div></div><div class="deck"><div><strong>36 + 24</strong><span>конфигурации в каждой ветке</span></div><div><strong>5 paired seeds</strong><span>все результаты, без выбора лучшего</span></div><div><strong>Train119: FAIL</strong><span>критерий применимости сохранили</span></div></div><div class="teaser-block">'''+media_video('04_story_teaser.mp4',placements[3]['caption'],'teaser')+'</div></header>'
    sources='''<section class="sources" id="sources"><div class="sources-inner"><h2>Источники и готовые материалы</h2><p>Эта страница работает без login, CDN и приватного project root. Видео запускаются только по вашей команде.</p><div class="download-row"><a href="text/LONGREAD_FULL.md" download>Полный текст</a><a href="text/LONGREAD_COMPACT.md" download>Короткая версия</a><a href="text/TELEGRAM_READY.md" download>Текст и порядок медиа</a></div><details><summary>Числа, границы вывода и воспроизводимость</summary><ul><li><a href="sources/CLAIM_FACTCHECK.tsv">Factcheck утверждений</a></li><li><a href="sources/MEDIA_SOURCE_MANIFEST.tsv">Источники медиа и хэши</a></li><li><a href="sources/STORYBOARD.md">Storyboard</a> · <a href="sources/VISUAL_SYSTEM.md">Visual system</a></li><li><a href="sources/RENDERING.md">Повторный рендер</a> · <a href="QA/VISUAL_QA_REPORT.md">Приёмка</a></li><li><a href="https://github.com/spicmaff/malonaldehyde-transition-sampling/releases/tag/v1.1.2">Сохранённая научная версия v1.1.2</a></li><li><a href="https://github.com/spicmaff/malonaldehyde-transition-sampling/releases/tag/v1.2.0">Presentation release v1.2.0</a></li></ul><p>Модели и scientific criteria не изменены. Новых DFT, обучения, inference/selector или динамики для оформления не выполнялось. Blind12 остаётся закрытым. Два endpoint overlaps, seed sensitivity, Validation11 caveats и terminal Train119 FAIL сохранены.</p></details></div></section>'''
    doc='<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="description" content="Малональдегид: одинаковый DFT-бюджет, переход протона, seed sensitivity и отрицательный итог Train119."><title>Куда поставить 24 DFT-точки? — Малональдегид</title><link rel="stylesheet" href="assets/style.css"></head><body><nav><a class="brand" href="#">МАЛОНАЛЬДЕГИД</a><div class="links"><a href="#chapter-1">Молекула</a><a href="#chapter-3">Результат</a><a href="#sources">Источники</a></div></nav>'+hero+'<main>'+''.join(content)+'</main>'+sources+'<footer class="footer"><div class="footer-inner"><span>Михаил Фофонов · malonaldehyde-transition-sampling</span><span>Сохранённые данные. Новая визуальная история. 2026.</span></div></footer><script src="assets/story.js"></script></body></html>'
    (out/'index.html').write_text(doc)
    (out/'START_HERE_RU.md').write_text('''# Откройте index.html

Дважды щёлкните `index.html`. Нужны соседние каталоги assets, media, text, sources и QA. Ничего устанавливать и входить в аккаунт не нужно. Нажмите Play на нужном ролике; звук отсутствует. «Сначала» возвращает к началу и запускает видео.

Если браузер запрещает локальное видео: откройте терминал в этой папке, выполните `python -m http.server 8000`, затем откройте http://localhost:8000 . На телефоне есть отдельный вертикальный ролик. Для полноэкранного просмотра воспользуйтесь нативной кнопкой video player.

Три основных MP4, teaser и вертикальная версия находятся в media. Готовые русские тексты и подписи — в text. Полные источники и повторный рендер — в sources. Визуальная и техническая приёмка — в QA.

Это презентационное обновление. Train119 остаётся STATIC_APPLICABILITY_FAIL. Молекулярное движение — визуальная интерполяция сохранённого NEB-пути; время просмотра не физическое время. Blind12 закрыт. Telegram автоматически не публиковался.
''')
    (out/'sources/EDITORIAL_COUNTS.json').write_text(json.dumps({'full_chars':len(full),'compact_chars':len(compact),'telegram_chars':len(telegram),'factcheck_rows':len(fact)},indent=2)+'\n')
    print('STORY_BUILT',out,'FULL_CHARS',len(full),'COMPACT',len(compact))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--data',type=Path,required=True);p.add_argument('--baseline',type=Path,required=True);p.add_argument('--out',type=Path,required=True);build(p.parse_args())
