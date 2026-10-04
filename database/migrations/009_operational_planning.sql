ALTER TABLE staff ADD COLUMN service_types text[] NOT NULL DEFAULT ARRAY['general_consultation']::text[] CHECK (cardinality(service_types)>0 AND service_types <@ ARRAY['general_consultation','follow_up','document_review','accessible_consultation']::text[]);
ALTER TABLE staff ADD COLUMN languages text[] NOT NULL DEFAULT ARRAY[]::text[] CHECK (languages <@ ARRAY['en','ta','si']::text[]);
ALTER TABLE queue_tokens ADD COLUMN service_type text NOT NULL DEFAULT 'general_consultation' CHECK (service_type IN ('general_consultation','follow_up','document_review','accessible_consultation'));
ALTER TABLE queue_tokens ADD COLUMN required_language text CHECK (required_language IN ('en','ta','si'));
ALTER TABLE queue_tokens ADD COLUMN preferred_staff_id uuid;
ALTER TABLE queue_tokens ADD COLUMN continuity_required boolean NOT NULL DEFAULT false;
ALTER TABLE queue_tokens ADD CONSTRAINT preferred_clinician_department FOREIGN KEY(preferred_staff_id,department_id) REFERENCES staff(id,department_id);
ALTER TABLE queue_tokens ADD CONSTRAINT continuity_clinician_required CHECK (NOT continuity_required OR preferred_staff_id IS NOT NULL);
