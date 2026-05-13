"use client";

import { useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { Copy, GitCompare, Heart, Loader2, Share2, Star, Trash2, UserPlus } from "lucide-react";
import {
  addWatchlistItem,
  compareSavedBuilds,
  createUserAccount,
  deleteSavedBuild,
  duplicateSavedBuild,
  listSavedBuilds,
  listWatchlist,
  removeWatchlistItem,
  updateSavedBuild
} from "@/lib/api";
import { getIdentity, getRecentBuilds, setStoredUser, type UserIdentity } from "@/lib/userSession";
import type { BuildComparisonResponse, SavedBuild, WatchlistItem } from "@/types/builder";

export function UserBuildsWorkspace() {
  const [identity, setIdentity] = useState<UserIdentity | null>(null);
  const [savedBuilds, setSavedBuilds] = useState<SavedBuild[]>([]);
  const [recentBuilds, setRecentBuilds] = useState<SavedBuild[]>([]);
  const [watchlist, setWatchlist] = useState<WatchlistItem[]>([]);
  const [selectedBuildIds, setSelectedBuildIds] = useState<string[]>([]);
  const [comparison, setComparison] = useState<BuildComparisonResponse | null>(null);
  const [email, setEmail] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [productId, setProductId] = useState("");
  const [targetPrice, setTargetPrice] = useState("");
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const resolvedIdentity = useMemo(
    () => ({
      user_id: identity?.user_id ?? null,
      guest_id: identity?.guest_id ?? null
    }),
    [identity]
  );

  useEffect(() => {
    const nextIdentity = getIdentity();
    setIdentity(nextIdentity);
    setRecentBuilds(getRecentBuilds());
  }, []);

  useEffect(() => {
    if (!identity) return;
    void refresh();
  }, [identity]);

  async function refresh() {
    if (!identity) return;
    setLoading(true);
    setMessage(null);
    try {
      const [builds, items] = await Promise.all([
        listSavedBuilds(resolvedIdentity),
        listWatchlist(resolvedIdentity, "SA")
      ]);
      setSavedBuilds(builds);
      setWatchlist(items);
      setRecentBuilds(getRecentBuilds());
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to load saved workspace.");
    } finally {
      setLoading(false);
    }
  }

  async function createAccount() {
    if (!email.trim()) {
      setMessage("Enter an email to create an optional account.");
      return;
    }
    setLoading(true);
    try {
      const user = await createUserAccount({ email, display_name: displayName || null, region: "SA" });
      setStoredUser(user);
      setIdentity(getIdentity());
      setMessage("Account ready. Future saved builds will attach to this user.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to create account.");
    } finally {
      setLoading(false);
    }
  }

  async function toggleFavorite(build: SavedBuild) {
    const updated = await updateSavedBuild(build.build_id, { favorite: !build.favorite });
    setSavedBuilds((current) => current.map((item) => (item.build_id === updated.build_id ? updated : item)));
  }

  async function duplicate(build: SavedBuild) {
    const next = await duplicateSavedBuild(build.build_id, resolvedIdentity);
    setSavedBuilds((current) => [next, ...current]);
  }

  async function remove(build: SavedBuild) {
    await deleteSavedBuild(build.build_id);
    setSavedBuilds((current) => current.filter((item) => item.build_id !== build.build_id));
    setSelectedBuildIds((current) => current.filter((id) => id !== build.build_id));
  }

  async function compare() {
    if (selectedBuildIds.length < 2) {
      setMessage("Select at least two saved builds to compare.");
      return;
    }
    setComparison(await compareSavedBuilds(selectedBuildIds, resolvedIdentity));
  }

  async function watchProduct() {
    if (!productId.trim()) {
      setMessage("Enter a product ID from a build component to track it.");
      return;
    }
    const items = await addWatchlistItem(resolvedIdentity, {
      product_id: productId.trim(),
      target_price_sar: targetPrice ? Number(targetPrice) : null,
      region: "SA"
    });
    setWatchlist(items);
    setProductId("");
    setTargetPrice("");
  }

  async function removeWatch(item: WatchlistItem) {
    await removeWatchlistItem(resolvedIdentity, item.item_id);
    setWatchlist((current) => current.filter((candidate) => candidate.item_id !== item.item_id));
  }

  function toggleSelected(buildId: string) {
    setSelectedBuildIds((current) =>
      current.includes(buildId) ? current.filter((item) => item !== buildId) : [...current, buildId].slice(-4)
    );
  }

  return (
    <section className="grid gap-4">
      <div className="rounded-lg border border-line bg-white p-4 shadow-tight">
        <div className="mb-3 flex flex-col gap-2 md:flex-row md:items-start md:justify-between">
          <div>
            <div className="text-xs font-semibold uppercase text-signal">User workspace</div>
            <h2 className="text-lg font-semibold text-ink">Saved Builds, Sharing, And Price Watchlist</h2>
            <p className="mt-1 max-w-3xl text-sm leading-6 text-muted">
              Browse as a guest, save builds locally and in the graph, then create an account when you want to revisit them later.
            </p>
          </div>
          <button
            type="button"
            onClick={refresh}
            className="inline-flex h-9 items-center justify-center rounded-md border border-line bg-panel px-3 text-sm font-semibold text-ink hover:bg-white"
          >
            {loading ? <Loader2 size={15} className="mr-2 animate-spin" aria-hidden /> : null}
            Refresh
          </button>
        </div>

        <div className="grid gap-3 lg:grid-cols-[1fr_1.4fr]">
          <div className="rounded-md border border-line bg-panel p-3">
            <div className="mb-2 flex items-center gap-2 text-sm font-semibold text-ink">
              <UserPlus size={16} aria-hidden />
              Optional account
            </div>
            {identity?.user ? (
              <p className="text-sm leading-6 text-muted">
                Signed in as <strong className="text-ink">{identity.user.display_name || identity.user.email}</strong>. Guest fallback remains active.
              </p>
            ) : (
              <div className="grid gap-2">
                <input
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                  placeholder="email@example.com"
                  className="h-10 rounded-md border border-line bg-white px-3 text-sm text-ink outline-none focus:border-signal"
                />
                <input
                  value={displayName}
                  onChange={(event) => setDisplayName(event.target.value)}
                  placeholder="Display name"
                  className="h-10 rounded-md border border-line bg-white px-3 text-sm text-ink outline-none focus:border-signal"
                />
                <button
                  type="button"
                  onClick={createAccount}
                  className="inline-flex h-10 items-center justify-center rounded-md border border-signal bg-signal px-3 text-sm font-semibold text-slate-950"
                >
                  Create Account
                </button>
              </div>
            )}
          </div>

          <div className="rounded-md border border-line bg-panel p-3">
            <div className="mb-2 text-sm font-semibold text-ink">Watch a Saudi product price</div>
            <div className="grid gap-2 md:grid-cols-[1fr_160px_auto]">
              <input
                value={productId}
                onChange={(event) => setProductId(event.target.value)}
                placeholder="Product ID"
                className="h-10 rounded-md border border-line bg-white px-3 text-sm text-ink outline-none focus:border-signal"
              />
              <input
                value={targetPrice}
                onChange={(event) => setTargetPrice(event.target.value)}
                placeholder="Target SAR"
                inputMode="numeric"
                className="h-10 rounded-md border border-line bg-white px-3 text-sm text-ink outline-none focus:border-signal"
              />
              <button
                type="button"
                onClick={watchProduct}
                className="inline-flex h-10 items-center justify-center rounded-md border border-line bg-white px-3 text-sm font-semibold text-ink"
              >
                Track
              </button>
            </div>
          </div>
        </div>

        {message ? <div className="mt-3 rounded-md border border-line bg-white px-3 py-2 text-sm text-muted">{message}</div> : null}
      </div>

      <div className="grid gap-4 xl:grid-cols-[1.3fr_0.9fr]">
        <Panel title="Saved Builds" actionLabel="Compare Selected" onAction={compare} actionDisabled={selectedBuildIds.length < 2}>
          {savedBuilds.length ? (
            <div className="grid gap-2">
              {savedBuilds.map((build) => (
                <SavedBuildRow
                  key={build.build_id}
                  build={build}
                  selected={selectedBuildIds.includes(build.build_id)}
                  onSelect={() => toggleSelected(build.build_id)}
                  onFavorite={() => void toggleFavorite(build)}
                  onDuplicate={() => void duplicate(build)}
                  onDelete={() => void remove(build)}
                />
              ))}
            </div>
          ) : (
            <EmptyState text="No saved builds yet. Generate a Saudi build and use Save Build." />
          )}
        </Panel>

        <Panel title="Build History">
          {recentBuilds.length ? (
            <div className="grid gap-2">
              {recentBuilds.map((build) => (
                <div key={build.build_id} className="rounded-md border border-line bg-panel p-3 text-sm">
                  <div className="font-semibold text-ink">{build.title}</div>
                  <div className="mt-1 text-xs text-muted">{formatSar(build.total_price_sar)} · {build.confidence_level} confidence</div>
                </div>
              ))}
            </div>
          ) : (
            <EmptyState text="Generated builds will appear here for guest continuity." />
          )}
        </Panel>
      </div>

      <div className="grid gap-4 xl:grid-cols-[1fr_1fr]">
        <Panel title="Comparison">
          {comparison ? (
            <div className="grid gap-2">
              {comparison.highlights.map((highlight) => (
                <div key={highlight} className="rounded-md border border-teal-200 bg-teal-50 px-3 py-2 text-sm text-signal">
                  {highlight}
                </div>
              ))}
              {comparison.compared_builds.map((build) => (
                <div key={build.build_id} className="rounded-md border border-line bg-panel p-3 text-sm">
                  <div className="font-semibold text-ink">{build.title}</div>
                  <div className="mt-1 text-xs leading-5 text-muted">
                    {formatSar(build.total_price_sar)} · {build.warning_count} warnings · {build.confidence_level} confidence
                  </div>
                  <div className="mt-2 flex flex-wrap gap-1">
                    {build.cheapest ? <Badge>Cheaper</Badge> : null}
                    {build.safest ? <Badge>Safer</Badge> : null}
                    {build.strongest ? <Badge>Stronger</Badge> : null}
                    {build.more_upgradeable ? <Badge>Upgradeable</Badge> : null}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <EmptyState text="Select two to four saved builds to compare price, confidence, and warnings." />
          )}
        </Panel>

        <Panel title="Favorites And Watchlist">
          {watchlist.length ? (
            <div className="grid gap-2">
              {watchlist.map((item) => (
                <div key={item.item_id} className="rounded-md border border-line bg-panel p-3 text-sm">
                  <div className="flex items-start justify-between gap-2">
                    <div>
                      <div className="font-semibold text-ink">{item.product_name || item.product_id}</div>
                      <div className="mt-1 text-xs leading-5 text-muted">
                        {formatSar(item.current_price_sar)} at {item.vendor || "unknown vendor"} · {item.status.replaceAll("_", " ")}
                      </div>
                    </div>
                    <button
                      type="button"
                      onClick={() => void removeWatch(item)}
                      className="inline-flex h-8 w-8 items-center justify-center rounded-md border border-line bg-white text-muted"
                      aria-label="Remove watchlist item"
                    >
                      <Trash2 size={14} aria-hidden />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <EmptyState text="Favorite products or enter a product ID to start tracking Saudi price changes." />
          )}
        </Panel>
      </div>
    </section>
  );
}

function Panel({
  title,
  children,
  actionLabel,
  onAction,
  actionDisabled
}: {
  title: string;
  children: ReactNode;
  actionLabel?: string;
  onAction?: () => void;
  actionDisabled?: boolean;
}) {
  return (
    <section className="rounded-lg border border-line bg-white p-4 shadow-tight">
      <div className="mb-3 flex items-center justify-between gap-3">
        <h2 className="text-base font-semibold text-ink">{title}</h2>
        {onAction && actionLabel ? (
          <button
            type="button"
            onClick={onAction}
            disabled={actionDisabled}
            className="inline-flex h-9 items-center gap-2 rounded-md border border-line bg-panel px-3 text-sm font-semibold text-ink disabled:cursor-not-allowed disabled:opacity-50"
          >
            <GitCompare size={15} aria-hidden />
            {actionLabel}
          </button>
        ) : null}
      </div>
      {children}
    </section>
  );
}

function SavedBuildRow({
  build,
  selected,
  onSelect,
  onFavorite,
  onDuplicate,
  onDelete
}: {
  build: SavedBuild;
  selected: boolean;
  onSelect: () => void;
  onFavorite: () => void;
  onDuplicate: () => void;
  onDelete: () => void;
}) {
  const shareUrl = build.share_slug ? `/build/share/${build.share_slug}` : "";
  return (
    <div className={`rounded-md border p-3 text-sm ${selected ? "border-signal bg-teal-50" : "border-line bg-panel"}`}>
      <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
        <button type="button" onClick={onSelect} className="min-w-0 text-left">
          <div className="font-semibold text-ink">{build.title}</div>
          <div className="mt-1 text-xs leading-5 text-muted">
            {formatSar(build.total_price_sar)} · {build.confidence_level} confidence · {build.warning_summary.length} warnings
          </div>
          {shareUrl ? <div className="mt-1 text-xs text-signal">{shareUrl}</div> : null}
        </button>
        <div className="flex shrink-0 flex-wrap gap-2">
          <IconButton label="Favorite" onClick={onFavorite}>
            {build.favorite ? <Star size={15} aria-hidden /> : <Heart size={15} aria-hidden />}
          </IconButton>
          <IconButton label="Duplicate" onClick={onDuplicate}>
            <Copy size={15} aria-hidden />
          </IconButton>
          <IconButton label="Share" onClick={() => void navigator.clipboard?.writeText(`${window.location.origin}${shareUrl}`)}>
            <Share2 size={15} aria-hidden />
          </IconButton>
          <IconButton label="Delete" onClick={onDelete}>
            <Trash2 size={15} aria-hidden />
          </IconButton>
        </div>
      </div>
    </div>
  );
}

function IconButton({ label, onClick, children }: { label: string; onClick?: () => void; children: ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="inline-flex h-8 w-8 items-center justify-center rounded-md border border-line bg-white text-muted hover:text-ink"
      aria-label={label}
      title={label}
    >
      {children}
    </button>
  );
}

function Badge({ children }: { children: ReactNode }) {
  return <span className="rounded border border-teal-200 bg-white px-1.5 py-0.5 text-[11px] font-semibold text-signal">{children}</span>;
}

function EmptyState({ text }: { text: string }) {
  return <div className="rounded-md border border-dashed border-line bg-panel px-3 py-6 text-center text-sm text-muted">{text}</div>;
}

function formatSar(value?: number | null) {
  if (value === null || value === undefined) return "Unavailable";
  return new Intl.NumberFormat("en-SA", {
    style: "currency",
    currency: "SAR",
    maximumFractionDigits: 0
  }).format(value);
}
