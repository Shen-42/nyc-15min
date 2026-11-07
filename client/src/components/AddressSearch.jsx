import { useEffect, useId, useRef, useState } from "react";
import { findAddresses } from "../data/geosearch";

// Typing waits this long after the last key before asking for suggestions.
const DEBOUNCE_MS = 250;
const MIN_LETTERS = 3;

const STATUS_TEXT = {
  loading: "Searching…",
  none: "No address in NYC matches that. Try a house number and street, like 120 Broadway.",
  error: "Address search isn't working right now. You can still click the map.",
};

// "Search an address": a way to pick a spot without the map, so keyboard
// and screen reader users can use the site too. It follows the ARIA
// combobox pattern: arrow keys move through the suggestions, Enter picks
// one, Escape closes the list (or clears the box if it's already closed).
// With the box empty, the list shows the last few spots looked at
// (heuristic 6), and pressing / anywhere jumps to the box (heuristic 7).
export default function AddressSearch({ onPick, recent = [] }) {
  const [text, setText] = useState("");
  const [results, setResults] = useState([]);
  const [status, setStatus] = useState(null); // a key of STATUS_TEXT, or null
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);
  // Set when a suggestion is picked, so filling the box with its label
  // doesn't start another search.
  const picked = useRef(false);
  const input = useRef(null);
  const id = useId();
  const listId = `${id}-list`;
  // An empty box lists recent spots; typing lists addresses.
  const showingRecent = text.trim() === "";
  const options = showingRecent ? recent : results;

  // "/" jumps to the box from anywhere, unless typing somewhere else.
  useEffect(() => {
    function onKey(event) {
      if (event.key !== "/" || event.ctrlKey || event.metaKey || event.altKey) return;
      const target = event.target;
      if (target.closest?.("input, textarea, select, [contenteditable='true'], dialog[open]")) return;
      event.preventDefault();
      input.current?.focus();
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

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
    if (event.key === "ArrowDown" && options.length) {
      event.preventDefault();
      setOpen(true);
      setActive((i) => (i + 1) % options.length);
    } else if (event.key === "ArrowUp" && options.length) {
      event.preventDefault();
      setOpen(true);
      setActive((i) => (i <= 0 ? options.length - 1 : i - 1));
    } else if (event.key === "Enter" && options.length && (open || !showingRecent)) {
      event.preventDefault();
      pick(options[Math.max(active, 0)]); // Enter alone takes the first suggestion
    } else if (event.key === "Escape") {
      if (open) setOpen(false);
      else setText("");
    }
  }

  const showList = open && options.length > 0;
  return (
    <div className="search" role="search">
      <label htmlFor={`${id}-input`} className="visually-hidden">
        Search an address in New York City
      </label>
      {/* The box, with an ✕ to clear it: phones don't all show one. */}
      <div className="search__field">
      <input
        ref={input}
        id={`${id}-input`}
        className="field__input search__input"
        type="search"
        role="combobox"
        aria-autocomplete="list"
        aria-expanded={showList}
        aria-controls={listId}
        aria-activedescendant={showList && active >= 0 ? `${listId}-${active}` : undefined}
        aria-keyshortcuts="/"
        placeholder="Search an address"
        autoComplete="off"
        enterKeyHint="search"
        value={text}
        onChange={(event) => {
          setText(event.target.value);
          setOpen(true);
          setActive(-1);
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        onKeyDown={onKeyDown}
      />
      {text && (
        <button
          type="button"
          className="search__clear"
          aria-label="Clear the search"
          onClick={() => {
            setText("");
            setResults([]);
            setActive(-1);
            input.current?.focus();
          }}
        >
          ✕
        </button>
      )}
      </div>
      {showList && (
        <ul id={listId} role="listbox" className="search__list" aria-label={showingRecent ? "Recent spots" : "Addresses"}>
          {showingRecent && (
            <li role="presentation" className="search__heading">
              Recent
            </li>
          )}
          {options.map((result, i) => (
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
        {open &&
          (showingRecent
            ? recent.length
              ? `${recent.length} recent spots. Use the arrow keys to choose.`
              : ""
            : status
              ? STATUS_TEXT[status]
              : results.length
                ? `${results.length} addresses. Use the arrow keys to choose.`
                : "")}
      </p>
    </div>
  );
}
