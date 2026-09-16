import type { ChildDocument, Deactivation, SetDocument } from "./types";

export interface SourceAdapter {
  loadChildren(): Promise<ChildDocument[]>;
  loadSets(): Promise<SetDocument[]>;
  loadDeactivations(): Promise<Deactivation[]>;
}
