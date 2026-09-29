import type { Ksztalt } from "../typy";

/**
 * The three silhouettes the map draws, as inline data URIs.
 *
 * Inline rather than files, because deck.gl wants a URL per icon and a build that fetches five
 * small images over HTTP fails in exactly the way that is hardest to see: the markers are simply
 * absent, the console says 404, and nothing else changes. These cannot 404.
 *
 * Each is a white silhouette on transparent, drawn pointing NORTH, and used as a MASK: deck.gl
 * fills the opaque pixels with whatever getColor returns, so one file serves every category colour.
 * That is also why each layer is drawn twice - once slightly larger in near-black as an outline,
 * once at size in the category colour. A mask cannot carry a second colour of its own, and without
 * the outline a dark red aircraft over dark blue water scores 2.46:1 against the basemap, which is
 * under the 3:1 a meaningful graphic needs.
 */

/**
 * width and height are NOT optional here, viewBox alone is not enough.
 *
 * deck.gl turns each icon URL into a bitmap with createImageBitmap, and that throws on an SVG with
 * no intrinsic size: "the image element contains an SVG image without natural dimensions". The
 * layer then renders nothing at all - no error on the map, no missing-image marker, just an empty
 * layer - which looked exactly like the icons had never been wired up.
 */
const svg = (tresc: string) =>
  "data:image/svg+xml;charset=utf-8," +
  encodeURIComponent(
    `<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 64 64">${tresc}</svg>`,
  );

/** Fixed-wing, seen from above: nose north, swept wings, tailplane. */
const SAMOLOT = svg(
  '<path fill="#fff" d="M32 3c2.3 0 4 3.4 4.3 8.6l.3 10.9 22.6 13.2c.7.4 1.1 1.2 1.1 2v4.6c0 .9-.9 1.6-1.8 1.3' +
  'l-22-6.7.4 12.4 7.3 5.4c.5.4.8 1 .8 1.6v2.7c0 .9-.8 1.5-1.6 1.3L32 57.6l-11.4 2.7c-.8.2-1.6-.4-1.6-1.3v-2.7' +
  'c0-.6.3-1.2.8-1.6l7.3-5.4.4-12.4-22 6.7c-.9.3-1.8-.4-1.8-1.3v-4.6c0-.8.4-1.6 1.1-2l22.6-13.2.3-10.9' +
  'C28 6.4 29.7 3 32 3z"/>',
);

/** Rotorcraft: short fuselage, tail boom, and a rotor disc that reads at eleven pixels. */
const SMIGLOWIEC = svg(
  '<path fill="#fff" d="M30.2 6h3.6c1 0 1.8.8 1.8 1.8v6.4h-7.2V7.8c0-1 .8-1.8 1.8-1.8z"/>' +
  '<rect fill="#fff" x="24.5" y="14.5" width="15" height="24" rx="7.5"/>' +
  '<rect fill="#fff" x="29.5" y="37" width="5" height="18"/>' +
  '<rect fill="#fff" x="22" y="52" width="20" height="4.5" rx="2.2"/>' +
  '<g fill="none" stroke="#fff" stroke-width="3.4" stroke-linecap="round">' +
  '<path d="M6 10 58 34"/><path d="M58 10 6 34"/></g>',
);

/** Vessel from above: pointed bow north, parallel sides, square transom. */
const STATEK = svg(
  '<path fill="#fff" d="M32 2.5c1 0 1.9.5 2.4 1.4l6.8 12c.5.9.8 1.9.8 2.9v34.4c0 1.6-1.3 2.9-2.9 2.9H24.9' +
  'c-1.6 0-2.9-1.3-2.9-2.9V18.8c0-1 .3-2 .8-2.9l6.8-12c.5-.9 1.4-1.4 2.4-1.4z"/>',
);

const OBRAZKI: Record<Ksztalt, string> = {
  samolot: SAMOLOT,
  smiglowiec: SMIGLOWIEC,
  statek: STATEK,
};

/** Near-black, the same value the callsign labels use, so outlines and text agree. */
export const OBWODKA: [number, number, number] = [17, 24, 33];

/** How much wider the outline is drawn than the mark it surrounds. */
export const GRUBOSC_OBWODKI = 3;

export function ikona(ksztalt: Ksztalt) {
  return { url: OBRAZKI[ksztalt], width: 64, height: 64, anchorX: 32, anchorY: 32, mask: true };
}

/**
 * The same silhouette for the legend, where CSS paints it instead of deck.gl.
 *
 * The key shows the mark exactly as the map draws it - same shape, same colour - by using the icon
 * as a CSS mask over the category colour. A legend that approximates its own map with a coloured
 * square is a legend the reader has to translate, and the translation is where they get it wrong.
 */
export function urlIkony(ksztalt: Ksztalt): string {
  return OBRAZKI[ksztalt];
}

/**
 * deck.gl measures getAngle anticlockwise from the icon as drawn; a compass bearing runs clockwise
 * from north. The silhouettes point north, so the bearing is simply negated. Getting this backwards
 * produces a map where everything sails the wrong way and still looks plausible, which is why it is
 * one function with a test rather than a minus sign repeated in three layers.
 */
export function kat(kursStopnie: number | null | undefined): number {
  return kursStopnie === null || kursStopnie === undefined || !Number.isFinite(kursStopnie)
    ? 0
    : -kursStopnie;
}
