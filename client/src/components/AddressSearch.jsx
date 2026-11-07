import { useEffect, useId, useRef, useState } from "react";
import { findAddresses } from "../data/geosearch";

// Typing waits this long after the last key before asking for suggestions.
const DEBOUNCE_MS = 250;
const MIN_LETTERS = 3;

const STATUS_TEXT = {
  loading: "Searching…",
  none: "No address in NYC matches that.",
  error: "Address search isn't working right now. You can still click the map.",
};

// "Search an address": a way to pick a spot without the map, so keyboard
// and screen reader users can use the site too. It follows the ARIA
// combobox pattern: arrow keys move through the suggestions, Enter picks
// one, Escape closes the list (or clears the box if it's already closed).
export default function AddressSearch({ onPick }) {
  const [text, setText] = useState("");
  const [results, setResults] = useState([]);
  const [status, setStatus] = useState(null); // a key of STATUS_TEXT, or null
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);
  // Set when a suggestion is picked, so filling the box with its label
  // doesn't start another search.
  const picked = useRef(false);
  const id = useId();
  const listId = `${id}-list`;

  useEffect(() => {
    const query = text.trim();
    if (picked.current) {
      picked.current = false;
      return;
    }
    if (query.length < MIN_LETTERS) {
      setResults([]);
      setStatus(null);
      return;
    }
    const controller = new AbortController();
    const timer = setTimeout(async () => {
      setStatus("loading");
      try {
        const found = await findAddresses(query, { signal: controller.signal });
        setResults(found);
        setActive(-1);
        setStatus(found.length ? null : "none");
      } catch (err) {
        if (err.name === "AbortError") return; // a newer keystroke took over
        setResults([]);
        setStatus("error");
      }
    }, DEBOUNCE_MS);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [text]);

  function pick(result) {
    picked.current = true;
    setText(result.label);
    setOpen(false);
    setActive(-1);
    onPick(result);
  }

  function onKeyDown(event) {
    if (event.key === "ArrowDown" && results.length) {
      event.preventDefault();
      setOpen(true);
      setActive((i) => (i + 1) % results.length);
    } else if (event.key === "ArrowUp" && results.length) {
      event.preventDefault();
      setOpen(true);
      setActive((i) => (i <= 0 ? results.length - 1 : i - 1));
    } else if (event.key === "Enter" && results.length) {
      event.preventDefault();
      pick(results[Math.max(active, 0)]); // Enter alone takes the first suggestion
    } else if (event.key === "Escape") {
      if (open) setOpen(false);
      else setText("");
    }
  }

  const showList = open && results.length > 0;
  return (
    <div className="search" role="search">
      <label htmlFor={`${id}-input`} className="visually-hidden">
        Search an address in New York City
      </label>
      <input
        id={`${id}-input`}
        className="field__input search__input"
        type="search"
        role="combobox"
        aria-autocomplete="list"
        aria-expanded={showList}
        aria-controls={listId}
        aria-activedescendant={showList && active >= 0 ? `${listId}-${active}` : undefined}
        placeholder="Search an address"
        autoComplete="off"
        enterKeyHint="search"
        value={text}
        onChange={(event) => {
          setText(event.target.value);
          setOpen(true);
        }}
        onFocus={() => results.length && setOpen(true)}
        onBlur={() => setOpen(false)}
        onKeyDown={onKeyDown}
      />
      {showList && (
        <ul id={listId} role="listbox" className="search__list" aria-label="Addresses">
          {results.map((result, i) => (
            <li
              key={`${result.label}-${i}`}
              id={`${listId}-${i}`}
              role="option"
              aria-selected={i === active}
              className="search__option"
              // mousedown, not click: a click would come after the box loses
              // focus, and losing focus closes the list.
              onMouseDown={(event) => {
                event.preventDefault();
                pick(result);
              }}
              onMouseEnter={() => setActive(i)}
            >
              {result.label}
            </li>
          ))}
        </ul>
      )}
      {/* Read out by screen readers: how many suggestions, or what went wrong. */}
      <p className={open && status ? "search__status" : "visually-hidden"} role="status">
        {open && (status ? STATUS_TEXT[status] : results.length ? `${results.length} addresses. Use the arrow keys to choose.` : "")}
      </p>
    </div>
  );
}
