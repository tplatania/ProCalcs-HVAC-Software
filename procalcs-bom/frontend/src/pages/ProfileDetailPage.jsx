/**
 * ProfileDetailPage.jsx — Create or edit a client profile
 * mode="create" | mode="edit"
 * Sections: Identity, Supplier, Markup, Brands, Part Name Overrides
 * Follows ProCalcs Design Standards v2.0
 */

import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useProfiles } from '../hooks/useProfiles'
import Button from '../components/Button'
import Spinner from '../components/Spinner'
import styles from './ProfileDetailPage.module.css'

const EMPTY_PROFILE = {
  client_id: '', client_name: '', is_active: true, notes: '',
  created_by: '',
  supplier: {
    supplier_name: '', account_number: '',
    mastic_cost_per_gallon: '', tape_cost_per_roll: '',
    strapping_cost_per_roll: '', screws_cost_per_box: '',
    brush_cost_each: '', flex_duct_cost_per_foot: '',
    rect_duct_cost_per_sqft: '',
  },
  markup: {
    equipment_pct: '', materials_pct: '',
    consumables_pct: '', labor_pct: '',
  },
  brands: {
    ac_brand: '', furnace_brand: '', air_handler_brand: '',
    mastic_brand: '', tape_brand: '', flex_duct_brand: '',
  },
  part_name_overrides: [],
  default_output_mode: 'full',
  include_labor: false,
}

export default function ProfileDetailPage({ mode }) {
  const navigate = useNavigate()
  const { clientId } = useParams()
  const { createProfile, updateProfile } = useProfiles()

  const [form, setForm]           = useState(EMPTY_PROFILE)
  const [isFetching, setIsFetching] = useState(mode === 'edit')
  const [isSaving, setIsSaving]   = useState(false)
  const [errors, setErrors]       = useState({})
  const [saveError, setSaveError] = useState(null)
  const [saved, setSaved]         = useState(false)

  // Load existing profile in edit mode
  useEffect(() => {
    if (mode !== 'edit' || !clientId) return
    async function fetchProfile() {
      const { apiFetch } = await import('../utils/apiFetch')
      const { success, data } = await apiFetch(`/api/v1/profiles/${clientId}`)
      if (success && data) {
        setForm({
          ...EMPTY_PROFILE, ...data,
          supplier: { ...EMPTY_PROFILE.supplier, ...(data.supplier || {}) },
          markup:   { ...EMPTY_PROFILE.markup,   ...(data.markup   || {}) },
          brands:   { ...EMPTY_PROFILE.brands,   ...(data.brands   || {}) },
          part_name_overrides: data.part_name_overrides || [],
        })
      }
      setIsFetching(false)
    }
    fetchProfile()
  }, [mode, clientId])

  // Generic field updater for nested objects
  function setField(section, key, value) {
    if (section) {
      setForm(prev => ({ ...prev, [section]: { ...prev[section], [key]: value } }))
    } else {
      setForm(prev => ({ ...prev, [key]: value }))
    }
    // Clear error on change
    setErrors(prev => ({ ...prev, [`${section ? section + '.' : ''}${key}`]: null }))
  }

  // Part name override helpers
  function addOverride() {
    setForm(prev => ({
      ...prev,
      part_name_overrides: [
        ...prev.part_name_overrides,
        { standard_name: '', client_name: '', client_sku: '' }
      ]
    }))
  }

  function updateOverride(index, field, value) {
    setForm(prev => {
      const updated = [...prev.part_name_overrides]
      updated[index] = { ...updated[index], [field]: value }
      return { ...prev, part_name_overrides: updated }
    })
  }

  function removeOverride(index) {
    setForm(prev => ({
      ...prev,
      part_name_overrides: prev.part_name_overrides.filter((_, i) => i !== index)
    }))
  }

  // Validate before save
  function validate() {
    const errs = {}
    if (!form.client_id?.trim())   errs['client_id']   = 'Client ID is required.'
    if (!form.client_name?.trim()) errs['client_name'] = 'Client name is required.'
    setErrors(errs)
    return Object.keys(errs).length === 0
  }

  // Save handler
  async function handleSave() {
    if (!validate()) return
    setIsSaving(true)
    setSaveError(null)

    const result = mode === 'create'
      ? await createProfile(form)
      : await updateProfile(clientId, form)

    setIsSaving(false)
    if (result.success) {
      setSaved(true)
      setTimeout(() => navigate('/profiles'), 1200)
    } else {
      setSaveError(result.error || 'Save failed. Please try again.')
    }
  }

  if (isFetching) return <Spinner fullPage label="Loading profile..." />

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <button className={styles.backBtn} onClick={() => navigate('/profiles')}>
          ← Back
        </button>
        <h1 className={styles.title}>
          {mode === 'create' ? 'New Client Profile' : `Edit — ${form.client_name || clientId}`}
        </h1>
      </header>

      {saveError && <div className={styles.errorBanner}>⚠ {saveError}</div>}
      {saved     && <div className={styles.successBanner}>✓ Saved! Redirecting...</div>}

      <div className={styles.sections}>

        {/* ── Identity ── */}
        <Section title="Client Identity">
          <Field label="Client ID *" error={errors['client_id']}
            hint="Unique identifier — must match Designer Desktop client ID">
            <input className={styles.input} value={form.client_id}
              disabled={mode === 'edit'}
              onChange={e => setField(null, 'client_id', e.target.value)}
              placeholder="e.g. beazer-001" />
          </Field>
          <Field label="Client Name *" error={errors['client_name']}>
            <input className={styles.input} value={form.client_name}
              onChange={e => setField(null, 'client_name', e.target.value)}
              placeholder="e.g. Beazer Homes" />
          </Field>
          <Field label="Created By">
            <input className={styles.input} value={form.created_by}
              onChange={e => setField(null, 'created_by', e.target.value)}
              placeholder="e.g. richard@procalcs.net" />
          </Field>
          <Field label="Status">
            <select className={styles.input} value={form.is_active ? 'active' : 'inactive'}
              onChange={e => setField(null, 'is_active', e.target.value === 'active')}>
              <option value="active">Active</option>
              <option value="inactive">Inactive</option>
            </select>
          </Field>
          <Field label="Notes">
            <textarea className={`${styles.input} ${styles.textarea}`}
              value={form.notes}
              onChange={e => setField(null, 'notes', e.target.value)}
              placeholder="Internal notes about this client's preferences..." />
          </Field>
        </Section>

        {/* ── Supplier ── */}
        <Section title="Supplier & Pricing">
          <TwoCol>
            <Field label="Supplier Name">
              <input className={styles.input} value={form.supplier.supplier_name}
                onChange={e => setField('supplier', 'supplier_name', e.target.value)}
                placeholder="e.g. Ferguson" />
            </Field>
            <Field label="Account Number">
              <input className={styles.input} value={form.supplier.account_number}
                onChange={e => setField('supplier', 'account_number', e.target.value)}
                placeholder="Optional" />
            </Field>
          </TwoCol>
          <p className={styles.sectionNote}>
            Enter what the client pays — ProCalcs applies markup on top.
          </p>
          <TwoCol>
            {[
              ['mastic_cost_per_gallon',  'Mastic ($/gal)'],
              ['tape_cost_per_roll',       'Foil Tape ($/roll)'],
              ['strapping_cost_per_roll',  'Strapping ($/roll)'],
              ['screws_cost_per_box',      'Screws ($/box)'],
              ['brush_cost_each',          'Mastic Brush ($/ea)'],
              ['flex_duct_cost_per_foot',  'Flex Duct ($/ft)'],
              ['rect_duct_cost_per_sqft',  'Rect Duct ($/sqft)'],
            ].map(([key, label]) => (
              <Field key={key} label={label}>
                <input className={styles.input} type="number" min="0" step="0.01"
                  value={form.supplier[key]}
                  onChange={e => setField('supplier', key, e.target.value)}
                  placeholder="0.00" />
              </Field>
            ))}
          </TwoCol>
        </Section>

        {/* ── Markup ── */}
        <Section title="Markup Tiers">
          <p className={styles.sectionNote}>Percentage markup applied per category.</p>
          <TwoCol>
            {[
              ['equipment_pct',   'Equipment (%)'],
              ['materials_pct',   'Materials (%)'],
              ['consumables_pct', 'Consumables (%)'],
              ['labor_pct',       'Labor (%)'],
            ].map(([key, label]) => (
              <Field key={key} label={label}>
                <input className={styles.input} type="number" min="0" step="0.1"
                  value={form.markup[key]}
                  onChange={e => setField('markup', key, e.target.value)}
                  placeholder="0.0" />
              </Field>
            ))}
          </TwoCol>
        </Section>

        {/* ── Brands ── */}
        <Section title="Brand Preferences">
          <p className={styles.sectionNote}>
            Preferred brand per category — applied automatically to consumable estimates.
          </p>
          <TwoCol>
            {[
              ['ac_brand',          'AC / Cooling'],
              ['furnace_brand',     'Furnace / Heating'],
              ['air_handler_brand', 'Air Handler'],
              ['mastic_brand',      'Mastic'],
              ['tape_brand',        'Foil Tape'],
              ['flex_duct_brand',   'Flex Duct'],
            ].map(([key, label]) => (
              <Field key={key} label={label}>
                <input className={styles.input} value={form.brands[key]}
                  onChange={e => setField('brands', key, e.target.value)}
                  placeholder="e.g. Carrier, Rectorseal..." />
              </Field>
            ))}
          </TwoCol>
        </Section>

        {/* ── Part Name Overrides ── */}
        <Section title="Part Name Overrides"
          action={<Button variant="secondary" size="sm" onClick={addOverride}>+ Add Override</Button>}>
          <p className={styles.sectionNote}>
            Map ProCalcs standard part names to this client's terminology and SKUs.
          </p>
          {form.part_name_overrides.length === 0 ? (
            <p className={styles.emptyOverrides}>No overrides configured yet.</p>
          ) : (
            <div className={styles.overrideList}>
              {form.part_name_overrides.map((o, i) => (
                <div key={i} className={styles.overrideRow}>
                  <input className={styles.input} value={o.standard_name}
                    onChange={e => updateOverride(i, 'standard_name', e.target.value)}
                    placeholder="Standard name (e.g. 4-inch collar)" />
                  <input className={styles.input} value={o.client_name}
                    onChange={e => updateOverride(i, 'client_name', e.target.value)}
                    placeholder="Their name (e.g. 4\" snap collar)" />
                  <input className={styles.input} value={o.client_sku}
                    onChange={e => updateOverride(i, 'client_sku', e.target.value)}
                    placeholder="Their SKU (e.g. FRG-COL-4IN)" />
                  <button className={styles.removeBtn} onClick={() => removeOverride(i)}
                    aria-label="Remove override">✕</button>
                </div>
              ))}
            </div>
          )}
        </Section>

        {/* ── Output Mode ── */}
        <Section title="Default Output Mode">
          <Field label="Default BOM output when generating">
            <select className={styles.input} value={form.default_output_mode}
              onChange={e => setField(null, 'default_output_mode', e.target.value)}>
              <option value="full">Full BOM (all items)</option>
              <option value="materials_only">Materials Only (no equipment)</option>
              <option value="client_proposal">Client Proposal (price only)</option>
              <option value="cost_estimate">Cost Estimate (internal)</option>
            </select>
          </Field>
        </Section>

      </div>

      <div className={styles.saveBar}>
        <Button variant="secondary" onClick={() => navigate('/profiles')}>Cancel</Button>
        <Button isLoading={isSaving} onClick={handleSave}>
          {mode === 'create' ? 'Create Profile' : 'Save Changes'}
        </Button>
      </div>
    </div>
  )
}

// ── Sub-components (kept small, single responsibility) ──

function Section({ title, children, action }) {
  return (
    <section className={styles.section}>
      <div className={styles.sectionHeader}>
        <h2 className={styles.sectionTitle}>{title}</h2>
        {action && <div>{action}</div>}
      </div>
      <div className={styles.sectionBody}>{children}</div>
    </section>
  )
}

function Field({ label, children, error, hint }) {
  return (
    <div className={styles.field}>
      <label className={styles.label}>{label}</label>
      {children}
      {hint  && <span className={styles.hint}>{hint}</span>}
      {error && <span className={styles.fieldError}>⚠ {error}</span>}
    </div>
  )
}

function TwoCol({ children }) {
  return <div className={styles.twoCol}>{children}</div>
}
