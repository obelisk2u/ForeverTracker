import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = { title: "How ForeverTracker works" };

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="flex flex-col gap-2">
      <h2 className="font-display text-xl text-gold">{title}</h2>
      <div className="text-muted flex flex-col gap-2 leading-relaxed">{children}</div>
    </section>
  );
}

export default function AboutPage() {
  return (
    <article className="max-w-3xl flex flex-col gap-8">
      <header>
        <h1 className="font-display text-3xl">How ForeverTracker works</h1>
        <p className="text-muted mt-2">This page is ForeverTracker&apos;s data collection policy.</p>
      </header>

      <Section title="Why a desktop app is needed">
        <p>
          World of Warcraft does not let addons connect to the internet. An addon can only save its data to a file on your
          computer, and the game writes that file only when you log out, exit or type /reload. Something outside the game
          therefore has to send your recorded runs to ForeverTracker.
        </p>
        <p>
          The ForeverTracker desktop app does this. When the game saves the file, the app uploads any new runs a few
          seconds later, so there is nothing to remember. It only reads the addon&apos;s file: it never changes anything in
          your WoW folder and does not interact with the game itself.
        </p>
        <p>
          You can pause it at any time, and it can show you exactly what it will send before sending it.{" "}
          <Link href="/download" className="underline">Get the desktop app</Link>.
        </p>
      </Section>

      <Section title="What is never collected">
        <p>
          No account or Battle.net names, no e-mail addresses, no chat or whispers, no real names and no payment
          information. Uploads are linked to a random installation ID created by the addon, not to a person. The
          ForeverTracker servers do not store IP addresses; they are used briefly in memory to limit upload rates.
        </p>
      </Section>

      <Section title="What the addon records">
        <ul className="list-disc pl-5 space-y-1">
          <li>The dungeon (map ID, name and difficulty) and when you entered and left it.</li>
          <li>Your group: character names and surnames, game character IDs (GUIDs), class, race, level and assigned role, and when each member joined or left.</li>
          <li>Everyone you group with outside dungeons too: their name, surname, game character ID, class and race (not their level).</li>
          <li>Boss encounters and whether they ended in a kill, and the completion event when the game sends one.</li>
          <li>Deaths of group members, seen as changes in their alive/dead state.</li>
          <li>Totals from Blizzard&apos;s built-in damage meter (damage, healing, interrupts, dispels, damage taken, deaths) once combat has ended and the game lets addons read them.</li>
          <li>Equipped items of you and of group members you can inspect, out of combat only.</li>
        </ul>
        <p>
          Everything comes from Blizzard&apos;s addon API, which only exposes what the game client shows you. The addon does
          not read game memory, inject code, automate gameplay, or make network requests.
        </p>
      </Section>
    </article>
  );
}
