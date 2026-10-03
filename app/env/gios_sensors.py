# Tylko stanowiska jednogodzinne (sprawdzone w API 3.10.2026). Bujaka 2771/2773, Bulwarowa 2793,
# Wadów 17310 i Swoszowice 20321 to pomiary dobowe (1 wartość/dobę, getData zwraca 400) — pomijamy.
GIOS_STATIONS = [
    # id,   nazwa,                   lat,       lon,       {PM10, PM2.5, NO2}
    (400,   "Al. Krasińskiego",      50.057678, 19.926189, {"pm10": 2750,  "pm25": 2752, "no2": 2747}),   # komunikacyjna
    (401,   "ul. Bujaka",            50.010575, 19.949189, {"pm10": 2770,  "no2": 2766}),                 # tło (PM2.5 tylko dobowy)
    (402,   "ul. Bulwarowa",         50.069308, 20.053492, {"pm10": 2792,  "pm25": 2794, "no2": 2788}),   # Nowa Huta
    (10123, "ul. Złoty Róg",         50.081197, 19.895358, {"pm10": 16786}),
    (10139, "Os. Piastów",           50.098508, 20.018269, {"pm10": 16784}),
    (10447, "Os. Wadów",             50.100569, 20.122561, {"pm10": 17309}),
    (11303, "Os. Swoszowice",        49.991442, 19.936792, {"pm10": 20320}),
    (16896, "ul. Kamieńskiego",      50.024605, 19.978460, {"pm10": 27841, "no2": 27843}),
]

# Stacja komunikacyjna: jej przyrost przy arterii modeluje f_road (kalibrowany z 400/401),
# więc nie wchodzi do przestrzennego tła (IDW), żeby nie liczyć ulicy dwa razy.
TRAFFIC_STATION = 400
BACKGROUND_STATION = 401
