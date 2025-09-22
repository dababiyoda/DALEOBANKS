import { pgTable, uuid, text, varchar, integer, real, timestamp, boolean, json } from "drizzle-orm/pg-core";
import { createInsertSchema } from "drizzle-zod";
import { z } from "zod";

export const tweets = pgTable("tweets", {
  id: varchar("id").primaryKey(),
  text: text("text").notNull(),
  kind: varchar("kind").notNull(), // proposal|reply|quote
  topic: text("topic"),
  hour_bin: integer("hour_bin"),
  cta_variant: text("cta_variant"),
  intensity: integer("intensity"),
  ref_tweet_id: varchar("ref_tweet_id"),
  created_at: timestamp("created_at").defaultNow(),
  likes: integer("likes").default(0),
  rts: integer("rts").default(0),
  replies: integer("replies").default(0),
  quotes: integer("quotes").default(0),
  authority_score: real("authority_score").default(0),
  j_score: real("j_score").default(0),
});

export const actions = pgTable("actions", {
  id: uuid("id").defaultRandom().notNull().primaryKey(),
  kind: varchar("kind").notNull(),
  meta_json: json("meta_json"),
  created_at: timestamp("created_at").defaultNow(),
});

export const kpis = pgTable("kpis", {
  id: uuid("id").defaultRandom().notNull().primaryKey(),
  name: varchar("name").notNull(),
  value: real("value").notNull(),
  period_start: timestamp("period_start").notNull(),
  period_end: timestamp("period_end").notNull(),
});

export const notes = pgTable("notes", {
  id: uuid("id").defaultRandom().notNull().primaryKey(),
  text: text("text").notNull(),
  created_at: timestamp("created_at").defaultNow(),
});

export const followers_snapshot = pgTable("followers_snapshot", {
  ts: timestamp("ts").primaryKey(),
  follower_count: integer("follower_count").notNull(),
});

export const redirects = pgTable("redirects", {
  id: uuid("id").defaultRandom().notNull().primaryKey(),
  label: text("label").notNull(),
  target_url: text("target_url").notNull(),
  utm: text("utm"),
  clicks: integer("clicks").default(0),
  revenue: real("revenue").default(0),
});

export const arms_log = pgTable("arms_log", {
  id: uuid("id").defaultRandom().notNull().primaryKey(),
  tweet_id: varchar("tweet_id"),
  post_type: varchar("post_type").notNull(),
  topic: text("topic"),
  hour_bin: integer("hour_bin"),
  cta_variant: text("cta_variant"),
  intensity: integer("intensity"),
  sampled_prob: real("sampled_prob"),
  reward_j: real("reward_j"),
  created_at: timestamp("created_at").defaultNow(),
});

export const persona_versions = pgTable("persona_versions", {
  version: integer("version").primaryKey(),
  hash: varchar("hash").notNull(),
  actor: text("actor"),
  payload: json("payload").notNull(),
  created_at: timestamp("created_at").defaultNow(),
});

// Insert schemas
export const insertTweetSchema = createInsertSchema(tweets).omit({
  created_at: true,
});

export const insertActionSchema = createInsertSchema(actions).omit({
  id: true,
  created_at: true,
});

export const insertKpiSchema = createInsertSchema(kpis).omit({
  id: true,
});

export const insertNoteSchema = createInsertSchema(notes).omit({
  id: true,
  created_at: true,
});

export const insertFollowersSnapshotSchema = createInsertSchema(followers_snapshot);

export const insertRedirectSchema = createInsertSchema(redirects).omit({
  id: true,
  clicks: true,
  revenue: true,
});

export const insertArmsLogSchema = createInsertSchema(arms_log).omit({
  id: true,
  created_at: true,
});

export const insertPersonaVersionSchema = createInsertSchema(persona_versions).omit({
  created_at: true,
});

// Types
export type Tweet = typeof tweets.$inferSelect;
export type InsertTweet = z.infer<typeof insertTweetSchema>;

export type Action = typeof actions.$inferSelect;
export type InsertAction = z.infer<typeof insertActionSchema>;

export type KPI = typeof kpis.$inferSelect;
export type InsertKPI = z.infer<typeof insertKpiSchema>;

export type Note = typeof notes.$inferSelect;
export type InsertNote = z.infer<typeof insertNoteSchema>;

export type FollowersSnapshot = typeof followers_snapshot.$inferSelect;
export type InsertFollowersSnapshot = z.infer<typeof insertFollowersSnapshotSchema>;

export type Redirect = typeof redirects.$inferSelect;
export type InsertRedirect = z.infer<typeof insertRedirectSchema>;

export type ArmsLog = typeof arms_log.$inferSelect;
export type InsertArmsLog = z.infer<typeof insertArmsLogSchema>;

export type PersonaVersion = typeof persona_versions.$inferSelect;
export type InsertPersonaVersion = z.infer<typeof insertPersonaVersionSchema>;
