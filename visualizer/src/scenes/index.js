/**
 * Scenes are imported from 19-diagrams/scenes -- the same files the SVG
 * renderer reads. Importing them rather than copying is the whole point: a
 * copy would drift, and the diagram in the README would start disagreeing with
 * the diagram in this app.
 *
 * Adding a system: drop the JSON in 19-diagrams/scenes/ and add it here.
 */
import urlShortener from '../../../19-diagrams/scenes/url-shortener.json'
import socialFeed from '../../../19-diagrams/scenes/social-feed.json'
import ticketBooking from '../../../19-diagrams/scenes/ticket-booking.json'

export const SCENES = [urlShortener, socialFeed, ticketBooking]
