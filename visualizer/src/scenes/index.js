/**
 * Scenes are imported from 19-diagrams/scenes -- the same files the SVG
 * renderer reads. Importing them rather than copying is the whole point: a
 * copy would drift, and the diagram in the README would start disagreeing with
 * the diagram in this app.
 *
 * Adding a system: drop the JSON in 19-diagrams/scenes/ and add it here.
 */
import urlShortener from '../../../19-diagrams/scenes/url-shortener.json'

export const SCENES = [urlShortener]
