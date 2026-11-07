import Dialog from "../account/Dialog";

// "About" (heuristic 10): what the site is for, where its data comes from,
// and what it can't tell you, in one short dialog next to Sign in.
export default function About({ open, onClose }) {
  return (
    <Dialog open={open} onClose={onClose} title="About this map">
      <div className="dialog__body about">
        <p>
          A 15-minute city is one where groceries, a pharmacy, a doctor, a park, a school, and transit are all within a
          15-minute walk. The idea comes from Carlos Moreno, a professor at the Sorbonne, and Paris took it up in 2020.
          This map lets anyone check how well a spot in New York meets it, and where it falls short.
        </p>
        <h3 className="about__heading">How to use it</h3>
        <p>
          Click anywhere in the five boroughs, or search an address. The shaded area is everywhere you can walk in 15
          minutes along real streets, and the score out of 100 says how much daily life is close by. Under Needs you
          can change what matters to you, or switch to wheelchair. Press / to jump to the search box.
        </p>
        <h3 className="about__heading">Where the data comes from</h3>
        <p>
          Streets, paths, and places are from OpenStreetMap, refreshed every month. Curb ramps are from NYC DOT,
          addresses from NYC Planning&rsquo;s GeoSearch, and the base map from Stadia Maps.
        </p>
        <h3 className="about__heading">What it can&rsquo;t tell you</h3>
        <p>
          OpenStreetMap misses some shops and clinics, and many places have no opening hours listed. The walk assumes
          a steady 3 mph on flat ground, with no waits at crossings, and it doesn&rsquo;t know about prices, quality,
          or whether a place is accessible inside.
        </p>
        <p>
          <a href="https://github.com/Shen-42/nyc-15min" target="_blank" rel="noreferrer">
            Source code and how it works, on GitHub
          </a>
        </p>
      </div>
    </Dialog>
  );
}
