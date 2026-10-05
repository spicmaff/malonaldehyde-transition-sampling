# Visual system v001

Фон #11171e; основной текст #edf0eb; вторичный #9caab4; линии #34434f.
Basin всегда #e5ae65; targeted всегда #65d2c7. Отказ #f58089. O #d6a8a1, C #78919f, H #dde2df, переносимый H* #f2d892: химические цвета имеют отдельную роль от стратегии sampling.

Ролики: DejaVu Sans / Bold, 66 px заголовок с ограничением ширины 1748 px; 30–43 px смысловые подписи; 22–29 px источники и необходимые caveats. RGB→H.264 yuv420p, 1920×1080 либо 1080×1920, 60 fps, faststart. Шрифт не включён бинарно: требуется DejaVu Sans (Bitstream Vera / DejaVu license), ссылка и лицензия в THIRD_PARTY_NOTICES.md.

Молекулярная сцена: spheres с Lambert-like shading и specular highlight, свет слева сверху. 7 backbone/C–H connections иллюстративны; пунктир O···H* обозначает направляющие расстояния. Atom identity неизменна. Kabsch fit: O0 C2 C4 C6 O7. Камера качается медленно в узком диапазоне; значения qPT и R(O···O) считаются в 3D, без display rotation.

Графики: все frozen sample points видны; соединения NEB — presentation interpolation, paired-seed lines — связь пары. γ inset явно увеличен около stop. Никаких искусственных осей времени или новых intermediate predictions.

Витрина: editorial typography, одна строка навигации, широкий hero и узкая колонка чтения. Светлая читательская область согласуется с тёмной сценой. Нативные video controls и Restart, без autoplay. Mobile имеет вертикальный fallback и внешние читаемые captions. Reduced motion отключает scroll animation; медиа запускает сам читатель. Зависимости: стандартные browser APIs, локальные assets; без CDN, login, API.
