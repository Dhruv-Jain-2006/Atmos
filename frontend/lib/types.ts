/**
 * Ergonomic aliases over the generated OpenAPI types.
 *
 * `types.gen.ts` is generated from `docs/openapi.json` and must never be edited
 * by hand. This file is the only place that reaches into its nested shape, so
 * components import readable names and a contract change surfaces here first.
 */

import type { components } from "./types.gen";

type Schemas = components["schemas"];

// Vocabulary
export type WeatherState = Schemas["WeatherState"];
export type Subdomain = Schemas["Subdomain"];
export type EpistemicStatus = Schemas["EpistemicStatus"];
export type EventType = Schemas["EventType"];
export type RelationshipType = Schemas["RelationshipType"];
export type RepoRelation = Schemas["RepoRelation"];
export type Vocabulary = Schemas["Vocabulary"];
export type WeatherStateInfo = Schemas["WeatherStateInfo"];
export type SubdomainInfo = Schemas["SubdomainInfo"];

// Measurement
export type DataFreshness = Schemas["DataFreshness"];
export type SignalSnapshot = Schemas["SignalSnapshot"];

// Trends
export type Trends = Schemas["Trends"];
export type WeatherOverview = Schemas["WeatherOverview"];
export type SubdomainClimate = Schemas["SubdomainClimate"];
export type TechnologyCard = Schemas["TechnologyCard"];
export type TechnologyList = Schemas["TechnologyList"];

// Research
export type TechnologyDetail = Schemas["TechnologyDetail"];
export type TechnologyHistory = Schemas["TechnologyHistory"];
export type HistoryPoint = Schemas["HistoryPoint"];
export type TechnologyRelationships = Schemas["TechnologyRelationships"];
export type RelatedTechnology = Schemas["RelatedTechnology"];
export type RepositorySensor = Schemas["RepositorySensor"];

// Events
export type EventSummary = Schemas["EventSummary"];
export type EventDetail = Schemas["EventDetail"];
export type EventList = Schemas["EventList"];
export type EvidenceLink = Schemas["EvidenceLink"];

// System
export type Health = Schemas["Health"];
export type SystemStatus = Schemas["SystemStatus"];
