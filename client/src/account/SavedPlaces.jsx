// "Saved places" in the settings (card 13): go back to one, or remove it.
export default function SavedPlaces({ places, onGo, onRemove }) {
  return (
    <details className="needs">
      <summary className="needs__summary">
        Saved places: <span className="needs__current">{places.length}</span>
      </summary>
      <div className="needs__body">
        {places.length === 0 ? (
          <p className="needs__note">Nothing saved yet. Use “Save this spot” under a score.</p>
        ) : (
          <ul className="saved-list">
            {places.map((place) => (
              <li key={place.id} className="saved-list__row">
                <button type="button" className="button button--link saved-list__go" onClick={() => onGo(place)}>
                  {place.name}
                </button>
                <button
                  type="button"
                  className="button saved-list__remove"
                  aria-label={`Remove ${place.name}`}
                  onClick={() => onRemove(place)}
                >
                  Remove
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </details>
  );
}
