/**
 * Parameter decisions, keyed by scene id.
 *
 * Deliberately a separate module from `scenes/index.js`, and the reason is
 * measured rather than stylistic. Every scene is imported into the app's main
 * bundle because the default view renders one immediately. The decision blocks
 * are 33 KB of prose that only the studio reads, and the studio is lazily
 * loaded -- so while they lived inside the scene files they were downloaded by
 * every visitor and read by almost none of them, costing 10.7 KB gzipped on the
 * critical path.
 *
 * Importing them here, and importing this file only from the studio, puts them
 * in the chunk that uses them. Nothing else changes: the files still sit in
 * 19-diagrams/scenes/decisions/ next to the scenes, and check_scenes.py
 * validates the pair together.
 */
import urlShortener from '../../../19-diagrams/scenes/decisions/url-shortener.json'
import socialFeed from '../../../19-diagrams/scenes/decisions/social-feed.json'
import ticketBooking from '../../../19-diagrams/scenes/decisions/ticket-booking.json'
import chatSystem from '../../../19-diagrams/scenes/decisions/chat-system.json'
import notificationSystem from '../../../19-diagrams/scenes/decisions/notification-system.json'
import paymentSystem from '../../../19-diagrams/scenes/decisions/payment-system.json'

const FILES = [
  urlShortener, socialFeed, ticketBooking,
  chatSystem, notificationSystem, paymentSystem,
]

export const DECISIONS = Object.fromEntries(
  FILES.map(f => [f.scene, f.decisions]),
)

/** The decisions for one scene, or an empty list if it has none yet. */
export function decisionsForScene(sceneId) {
  return DECISIONS[sceneId] ?? []
}
