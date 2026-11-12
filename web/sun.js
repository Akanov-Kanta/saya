// The same NOAA solar position formulas as sun.py, so the 3D lighting and the
// daylight curve can follow the slider instantly. The shade used for routing
// still comes from Python.

export function sunPosition(date, lat, lon) {
  const start = Date.UTC(date.getUTCFullYear(), 0, 1);
  const dayOfYear = Math.floor((date.getTime() - start) / 86400000) + 1;
  const hour = date.getUTCHours() + date.getUTCMinutes() / 60 + date.getUTCSeconds() / 3600;
  const g = (2 * Math.PI / 365) * (dayOfYear - 1 + (hour - 12) / 24);
  const eqtime = 229.18 * (0.000075 + 0.001868 * Math.cos(g) - 0.032077 * Math.sin(g)
    - 0.014615 * Math.cos(2 * g) - 0.040849 * Math.sin(2 * g));
  const decl = 0.006918 - 0.399912 * Math.cos(g) + 0.070257 * Math.sin(g)
    - 0.006758 * Math.cos(2 * g) + 0.000907 * Math.sin(2 * g)
    - 0.002697 * Math.cos(3 * g) + 0.00148 * Math.sin(3 * g);
  const trueSolarTime = hour * 60 + eqtime + 4 * lon;
  const hourAngle = (trueSolarTime / 4 - 180) * Math.PI / 180;
  const phi = lat * Math.PI / 180;
  const cosZenith = Math.sin(phi) * Math.sin(decl) + Math.cos(phi) * Math.cos(decl) * Math.cos(hourAngle);
  const altitude = 90 - Math.acos(Math.max(-1, Math.min(1, cosZenith))) * 180 / Math.PI;
  const azimuth = Math.atan2(Math.sin(hourAngle),
    Math.cos(hourAngle) * Math.sin(phi) - Math.tan(decl) * Math.cos(phi)) * 180 / Math.PI + 180;
  return { altitude, azimuth: ((azimuth % 360) + 360) % 360 };
}

export function compass(azimuth) {
  const names = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW'];
  return names[Math.floor((((azimuth % 360) + 360) % 360 + 22.5) / 45) % 8];
}

export function astanaDate(date, minutes) {
  const hh = String(Math.floor(minutes / 60)).padStart(2, '0');
  const mm = String(minutes % 60).padStart(2, '0');
  return new Date(`${date}T${hh}:${mm}:00+05:00`);
}
