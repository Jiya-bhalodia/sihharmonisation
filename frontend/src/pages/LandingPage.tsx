import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { Bar, BarChart, CartesianGrid, Cell, Legend, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import MapView from "../components/MapView";
import { useApi } from "../hooks/useApi";
import { api } from "../services/api";
import { displayDatasetName } from "../services/displayNames";
import { buildLayerConfig, parcelsToFeatures } from "../services/geo";
import type { UnifiedParcel } from "../types";

import {
  AlertTriangle,
  ArrowDown,
  ArrowRight,
  ArrowUpRight,
  Braces,
  Building2,
  Cable,
  Check,
  ChevronDown,
  CircleCheck,
  Code2,
  Crosshair,
  Database,
  Eye,
  FileStack,
  GitBranch,
  GitMerge,
  Landmark,
  Map,
  MapPin,
  Menu,
  MousePointer2,
  Network,
  PanelLeft,
  RefreshCw,
  Route,
  ScanLine,
  Search,
  Server,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  Target,
  Workflow,
  X,
} from "lucide-react";

const capabilities = [
  { n: "01", title: "AI spatial matching", desc: "Identify corresponding parcels, buildings, roads and features across heterogeneous spatial datasets.", icon: GitMerge, crop: "16% 48%" },
  { n: "02", title: "Automated topology correction", desc: "Detect gaps, overlaps, slivers and invalid geometries — then surface precise corrections.", icon: ScanLine, crop: "50% 42%" },
  { n: "03", title: "Intelligent attribute mapping", desc: "Understand inconsistent schemas, field names and classification systems across departments.", icon: Braces, crop: "82% 46%" },
  { n: "04", title: "Coordinate intelligence", desc: "Detect coordinate reference systems and transform datasets into a common spatial reference.", icon: Crosshair, crop: "22% 78%" },
  { n: "05", title: "Change detection", desc: "Compare historical and current datasets to identify changes in structures, boundaries and land use.", icon: RefreshCw, crop: "62% 77%" },
  { n: "06", title: "Confidence scoring", desc: "Assign confidence levels to harmonized features so operators can prioritize validation.", icon: Target, crop: "91% 70%" },
];

const workflow = [
  ["01", "Ingest", "Upload or connect heterogeneous spatial and non-spatial datasets."],
  ["02", "Understand", "AI identifies geometry, schema, CRS, metadata and feature types."],
  ["03", "Match", "Spatial AI identifies corresponding features across datasets."],
  ["04", "Harmonize", "Geometry, attributes and coordinate systems are normalized."],
  ["05", "Validate", "Topology rules, spatial conflicts and anomalies are automatically detected."],
  ["06", "Score", "Every integrated feature receives a confidence score."],
  ["07", "Synchronize", "Validated outputs are published to downstream land information systems."],
];


const architecture = [
  { number: "01", title: "DATA SOURCES", description: "Connect to field devices, databases and third-party systems.", icon: Database, href: "/data-sources", action: "Open data sources" },
  { number: "02", title: "DATA INGESTION", description: "Secure, reliable pipelines for real-time and batch ingestion.", icon: FileStack, href: "/data-sources", action: "Open data ingestion" },
  { number: "03", title: "ETL / NORMALIZATION", description: "Standardize, enrich and validate data for downstream use.", icon: GitBranch, href: "/harmonization", action: "Open normalization" },
  { number: "04", title: "SPATIAL AI ENGINE", description: "AI models and spatial analytics that turn data into actionable intelligence.", icon: Sparkles, href: "/spatial-matching", action: "Open spatial AI" },
  { number: "05", title: "FEATURE MATCHING", description: "Match and reconcile features across datasets with confidence.", icon: GitMerge, href: "/spatial-matching", action: "Open feature matching" },
  { number: "06", title: "TOPOLOGY VALIDATION", description: "Ensure geometric integrity and topological correctness at scale.", icon: ShieldCheck, href: "/topology", action: "Open topology validation" },
  { number: "07", title: "CONFLICT RESOLUTION", description: "Detect, prioritize and resolve conflicts with auditability.", icon: AlertTriangle, href: "/conflicts", action: "Open conflict resolution" },
  { number: "08", title: "CONFIDENCE ENGINE", description: "Score and rank results with explainable confidence metrics.", icon: Target, href: "/reports", action: "Open confidence reports" },
  { number: "09", title: "SPATIAL DATABASE", description: "High-performance storage optimized for spatial workloads.", icon: Server, href: "/records", action: "Open spatial records" },
  { number: "10", title: "WEB GIS / API / EXPORT", description: "Deliver insights where teams work—maps, APIs and exports.", icon: Network, href: "/records", action: "Open Web GIS records" },
];

const useCases = [
  ["Urban land records", "Cadastral harmonization and parcel validation.", Landmark],
  ["Municipal GIS", "Integrate property, infrastructure and planning datasets.", Building2],
  ["Utility mapping", "Synchronize utility networks with land and building data.", Cable],
  ["Survey validation", "Compare GNSS/CORS, drone and cadastral observations.", Crosshair],
  ["Change monitoring", "Detect changes between historical and current datasets.", Eye],
  ["Land governance", "Create interoperable spatial data infrastructure.", Map],
];

function scrollToId(id: string) {
  document.querySelector(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
}

function SectionLabel({ number, children, light = false }: { number: string; children: React.ReactNode; light?: boolean }) {
  return <div className={`section-label ${light ? "section-label-light" : ""}`}><span>{number}</span><i />{children}</div>;
}

function Reveal({ children, className = "", delay = 0 }: { children: React.ReactNode; className?: string; delay?: number }) {
  return <div className={`reveal ${className}`} style={{ "--reveal-delay": `${delay}ms` } as React.CSSProperties}>{children}</div>;
}

export default function Home() {
  const [activeSection, setActiveSection] = useState("hero");
  const [selectedParcel, setSelectedParcel] = useState<UnifiedParcel | null>(null);
  const [showParcelLayer, setShowParcelLayer] = useState(true);
  const [beforeAfter, setBeforeAfter] = useState(50);
  const [activeWorkflow, setActiveWorkflow] = useState(0);
  const [activeArchitecture, setActiveArchitecture] = useState("04");
  const { data: liveStats, loading: statsLoading, error: statsError } = useApi(() => api.getStatistics());
  const { data: liveParcels, loading: parcelsLoading } = useApi(() => api.getParcels({ limit: 300 }));
  const { data: liveDatasets, loading: datasetsLoading } = useApi(() => api.getDatasets());
  const parcelFeatures = useMemo(() => liveParcels ? parcelsToFeatures(liveParcels) : [], [liveParcels]);
  const mapLayers = useMemo(() => [buildLayerConfig("dashboard-unified", "unified", parcelFeatures, showParcelLayer)], [parcelFeatures, showParcelLayer]);
  const progressRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const onScroll = () => {
      const doc = document.documentElement;
      const max = doc.scrollHeight - window.innerHeight;
      if (progressRef.current) progressRef.current.style.width = `${max > 0 ? (window.scrollY / max) * 100 : 0}%`;
      const ids = ["hero", "challenge", "idea", "capabilities", "workflow", "gis", "comparison", "architecture", "use-cases", "interoperability"];
      let current = "hero";
      ids.forEach((id) => { const el = document.getElementById(id); if (el && el.getBoundingClientRect().top < window.innerHeight * .38) current = id; });
      setActiveSection(current);
      const workflowSection = document.getElementById("workflow");
      if (workflowSection) {
        const bounds = workflowSection.getBoundingClientRect();
        const progress = Math.max(0, Math.min(1, (window.innerHeight * 0.58 - bounds.top) / Math.max(1, bounds.height - window.innerHeight * 0.42)));
        const step = Math.min(workflow.length - 1, Math.floor(progress * workflow.length));
        setActiveWorkflow((currentStep) => currentStep === step ? currentStep : step);
      }
    };
    const observer = new IntersectionObserver((entries) => entries.forEach((entry) => { if (entry.isIntersecting) entry.target.classList.add("is-visible"); }), { threshold: .12 });
    document.querySelectorAll(".reveal").forEach((el) => observer.observe(el));
    window.addEventListener("scroll", onScroll, { passive: true });
    onScroll();
    return () => { observer.disconnect(); window.removeEventListener("scroll", onScroll); };
  }, []);

  const handleMapFeatureClick = (properties: Record<string, unknown>) => {
    const selected = liveParcels?.find((parcel) => parcel.id === String(properties.id));
    if (selected) setSelectedParcel(selected);
  };

  const confidenceData = liveStats ? Object.entries(liveStats.confidence_distribution).map(([name, value]) => ({ name, value })) : [];
  const distributionData = liveStats?.dataset_feature_distribution.map((item) => ({
    name: displayDatasetName(item.name).length > 16 ? `${displayDatasetName(item.name).slice(0, 14)}…` : displayDatasetName(item.name),
    count: item.count,
  })) || [];
  const qualityData = liveStats?.data_quality_scores.map((item) => ({
    name: displayDatasetName(item.name).length > 18 ? `${displayDatasetName(item.name).slice(0, 16)}…` : displayDatasetName(item.name),
    score: item.quality_score,
  })) || [];
  const conflictData = liveStats ? Object.entries(liveStats.conflict_categories).map(([name, value]) => ({ name: name.replace(/_/g, " "), value })) : [];
  const confidenceColors = ["#73866e", "#c99370", "#a65e43"];


  return (
    <div className="site-shell">
      <div className="scroll-progress" ref={progressRef} />
      <div className="landing-content">
        <section id="hero" className="hero-section">
          <div className="hero-grid" /><div className="hero-vignette" /><div className="hero-noise" />
          <div className="hero-map-lines"><span /><span /><span /><span /><span /><span /></div>
          <svg className="hero-cadastral-map" viewBox="0 0 1600 900" preserveAspectRatio="xMidYMid slice" aria-hidden="true" focusable="false">
            <g className="hero-map-roads">
              <path d="M-80 690 C210 570 310 635 520 500 S880 410 1070 260 1390 190 1690 50" />
              <path d="M80 940 C300 740 460 690 660 700 S980 610 1160 500 1430 460 1680 320" />
              <path d="M-50 240 C180 320 380 260 580 320 S900 450 1080 410 1380 290 1650 370" />
              <path d="M460 -40 C520 180 610 330 700 470 S790 720 900 950" />
              <path d="M1260 -50 C1180 170 1230 310 1320 470 S1400 730 1510 950" />
            </g>
            <g className="hero-map-parcels">
              <path d="M90 170 220 135 260 245 125 278Z M235 128 370 110 410 224 274 244Z M385 104 520 145 485 265 425 230Z" />
              <path d="M65 300 195 278 222 408 85 438Z M214 270 345 254 375 382 242 406Z M394 257 520 285 495 405 390 385Z" />
              <path d="M270 445 390 420 438 535 308 572Z M452 420 580 402 620 518 470 535Z M635 405 760 430 720 548 622 520Z" />
              <path d="M820 115 950 78 990 205 850 245Z M980 70 1110 88 1150 205 1005 210Z M1170 90 1300 50 1340 170 1190 208Z" />
              <path d="M900 270 1035 232 1080 350 940 392Z M1090 230 1210 215 1255 335 1100 352Z M1270 218 1400 245 1370 365 1260 338Z" />
              <path d="M1040 445 1170 408 1212 530 1082 570Z M1220 390 1350 375 1395 495 1240 528Z M1410 375 1535 420 1490 540 1402 500Z" />
              <path d="M720 630 850 585 895 715 760 748Z M910 590 1040 570 1080 695 930 720Z M1100 585 1230 605 1260 728 1112 705Z" />
              <path d="M250 650 390 610 425 735 285 770Z M450 600 590 590 628 710 470 738Z M640 580 735 610 710 730 630 712Z" />
              <path d="M1320 610 1450 570 1500 690 1360 730Z M1480 565 1610 600 1570 730 1500 700Z" />
            </g>
          </svg>
          <div className="hero-copy container">
            <Reveal><div className="eyebrow hero-eyebrow"><span className="eyebrow-dot" />Geospatial intelligence / urban land governance</div></Reveal>
            <Reveal delay={80}><h1>Every parcel.<br /><em>One intelligent</em><br />spatial truth.</h1></Reveal>
            <Reveal delay={150}><p className="hero-description">BHUMI-X automatically integrates fragmented land datasets into a validated, synchronized and confidence-scored urban land information system.</p></Reveal>
            <Reveal delay={220}><div className="hero-actions"><Link className="button button-light" to="/data-sources">Open tools <ArrowUpRight size={16} /></Link><a className="text-link text-link-light" href="#idea">See how it works <ArrowDown size={15} /></a></div></Reveal>
          </div>
          <div className="hero-meta container"><span>AI / GIS / COMPUTER VISION / SPATIAL ETL</span><span className="hero-meta-right">Naks<span>h</span>a-ready geospatial workflow <i /></span></div>
          <div className="hero-coord coord-one">LIVE DATASETS<br />{liveStats?.total_datasets ?? "—"} CONNECTED SOURCES</div><div className="hero-coord coord-two">UNIFIED PARCELS<br />{liveStats?.total_parcels ?? "—"} RECORDS</div>
          <div className="hero-scroll"><span>Scroll to explore</span><span className="scroll-line" /></div>
        </section>

        <section id="challenge" className="section section-cream challenge-section">
          <div className="container"><SectionLabel number="01">The challenge</SectionLabel><div className="challenge-grid"><Reveal><h2>Bringing city land data together is <span>harder than it should be.</span></h2></Reveal><Reveal delay={100}><div className="challenge-copy"><p>Cadastral records rely on survey, revenue, municipal and utility data. Different coordinate systems, parcel identifiers and update cycles make these sources difficult to align and validate.</p><p>Teams spend valuable time reconciling layers and checking conflicts before records are ready to use.</p><a className="text-link" href="#idea">See how harmonization helps <ArrowUpRight size={15} /></a></div></Reveal></div><div className="challenge-issues">{[["01", "Misaligned maps", "Drone, ORI, GNSS and cadastral layers arrive in different coordinate systems."], ["02", "Conflicting boundaries", "Overlaps, gaps and duplicate parcel shapes make ownership and extent unclear."], ["03", "Inconsistent records", "Departments use different IDs, names, attributes and data formats for the same place."], ["04", "Slow manual checks", "Staff spend time matching layers and correcting topology instead of validating priority cases."]].map(([number, title, desc]) => <article className="challenge-issue" key={number}><span>{number}</span><div><h3>{title}</h3><p>{desc}</p></div><ArrowUpRight size={16} /></article>)}</div><div className="challenge-data-strip"><span>DRONE / ORI</span><i /><span>GNSS / CORS</span><i /><span>CADASTRAL</span><i /><span>MUNICIPAL / REVENUE</span><i /><span>UTILITIES / GT</span></div></div>
        </section>

        <section id="idea" className="section idea-section idea-manifesto" aria-labelledby="idea-title">
          <div className="idea-manifesto-sheet">
            <header className="manifesto-topline">
              <span><i />02&nbsp; / &nbsp;BHUMI-X / SPATIAL INTELLIGENCE</span>
              <span className="manifesto-tagline"><i />A MORE GROUNDED TOMORROW</span>
            </header>

            <div className="manifesto-intro">
              <h2 id="idea-title">From fragmented<br />layers<br /><em>to one spatial<br />intelligence layer.</em></h2>
              <div className="manifesto-summary">
                <p>BHUMI-X creates a shared spatial reference across the datasets that define a city — without hiding uncertainty or breaking provenance.</p>
                <span />
              </div>
            </div>

            <div className="manifesto-diagram" aria-label="Exploded map layers converge through spatial processing into one unified isometric city map">
              <svg className="manifesto-map-illustration" viewBox="0 0 1100 380" role="img" aria-labelledby="manifesto-map-title manifesto-map-desc">
                <title id="manifesto-map-title">Spatial layers converge into one city map</title>
                <desc id="manifesto-map-desc">Five detailed map surfaces for drone, satellite, elevation, municipal and utility data align into a clean unified parcel map.</desc>
                <defs>
                  <pattern id="texture-drone-plane" width="58" height="38" patternUnits="userSpaceOnUse">
                    <rect width="58" height="38" fill="#e8e8d9"/><path d="M0 8 14 3 22 8 9 14ZM31 2 47 0 53 7 38 12ZM16 24 29 19 37 24 24 31ZM42 20 58 16V29L48 34Z" fill="#c9cfba" stroke="#a3ad97" strokeWidth=".8"/><path d="M0 19 12 16M30 37 39 31M23 0 26 9M4 31 12 26" fill="none" stroke="#f5f1e6" strokeWidth="2"/><circle cx="5" cy="5" r="2" fill="#879579"/><circle cx="55" cy="10" r="2" fill="#879579"/>
                  </pattern>
                  <pattern id="texture-satellite-plane" width="72" height="44" patternUnits="userSpaceOnUse">
                    <rect width="72" height="44" fill="#dfe5d7"/><path d="M-4 6 18 0 34 7 23 20 2 18ZM38 -3 68 4 75 17 53 21 35 12ZM-4 26 20 21 36 35 18 47ZM40 24 66 20 76 33 55 47 36 38Z" fill="#becbb1" stroke="#9cab91" strokeWidth=".9"/><path d="M31 -2C27 11 37 17 32 26S28 38 35 46" fill="none" stroke="#c3d8d1" strokeWidth="4"/><path d="M0 40 72 4" fill="none" stroke="#eee9d9" strokeWidth="1.5"/>
                  </pattern>
                  <pattern id="texture-elevation-plane" width="62" height="44" patternUnits="userSpaceOnUse">
                    <rect width="62" height="44" fill="#e7e9dc"/><path d="M-8 14C4 2 17 2 27 14S48 27 68 8M-7 20C6 8 17 8 26 19S47 33 68 14M-5 27C7 15 18 16 27 26S46 39 68 21M3 36C14 25 23 25 31 34S47 43 58 34" fill="none" stroke="#aab49b" strokeWidth=".85"/><path d="M18 44C23 36 30 35 35 41S48 48 54 41" fill="none" stroke="#c4cbb5" strokeWidth="1.1"/>
                  </pattern>
                  <pattern id="texture-municipal-plane" width="52" height="38" patternUnits="userSpaceOnUse">
                    <rect width="52" height="38" fill="#ece9dc"/><path d="M0 0H22V16H0ZM28 0H52V11H28ZM0 22H16V38H0ZM22 22H39V38H22ZM45 17H52V38H45Z" fill="#e0dfd1" stroke="#aeb3a2" strokeWidth=".8"/><path d="M24 0V38M0 19H52" fill="none" stroke="#f7f4eb" strokeWidth="2.2"/><path d="M39 11V17H45" fill="none" stroke="#c1b89f" strokeWidth="1"/>
                  </pattern>
                  <pattern id="texture-utilities-plane" width="64" height="42" patternUnits="userSpaceOnUse">
                    <rect width="64" height="42" fill="#e9e8dd"/><path d="M-3 32 12 24 27 27 42 12 68 8M5 -2 15 10 12 24M35 45 27 27 39 20 50 26 59 14" fill="none" stroke="#739b8a" strokeWidth="1.25"/><path d="M-2 12 12 17 26 8 42 12 62 0" fill="none" stroke="#b88968" strokeWidth=".9"/><circle cx="12" cy="24" r="2.1" fill="#66897a"/><circle cx="27" cy="27" r="2.1" fill="#66897a"/><circle cx="42" cy="12" r="2.1" fill="#b88968"/><circle cx="50" cy="26" r="1.8" fill="#66897a"/>
                  </pattern>
                  <clipPath id="input-drone"><polygon points="270,14 408,54 270,94 132,54" /></clipPath>
                  <clipPath id="input-satellite"><polygon points="270,80 408,120 270,160 132,120" /></clipPath>
                  <clipPath id="input-elevation"><polygon points="270,146 408,186 270,226 132,186" /></clipPath>
                  <clipPath id="input-municipal"><polygon points="270,212 408,252 270,292 132,252" /></clipPath>
                  <clipPath id="input-utilities"><polygon points="270,278 408,318 270,358 132,318" /></clipPath>
                  <clipPath id="processing-top"><polygon points="600,82 720,122 600,162 480,122" /></clipPath>
                  <clipPath id="processing-middle"><polygon points="600,126 720,166 600,206 480,166" /></clipPath>
                  <clipPath id="processing-lower"><polygon points="600,170 720,210 600,250 480,210" /></clipPath>
                  <clipPath id="processing-base"><polygon points="600,214 720,254 600,294 480,254" /></clipPath>
                  <clipPath id="city-map"><polygon points="880,98 1030,182 880,274 730,182" /></clipPath>
                </defs>

                <g className="isometric-input-layer input-layer-drone">
                  <text x="20" y="58">DRONE</text><path className="map-leader" d="M77 54H126"/><circle cx="128" cy="54" r="2"/>
                  <polygon points="270,14 408,54 270,94 132,54" className="map-plane map-plane-drone"/>
                  <g clipPath="url(#input-drone)" className="map-detail map-detail-drone"><path d="M145 58 218 32 273 70 331 30 397 55M183 20 236 86M302 18 290 89M355 29 341 81"/><circle cx="222" cy="52" r="3"/><circle cx="256" cy="42" r="5"/><circle cx="305" cy="66" r="4"/><circle cx="333" cy="47" r="3"/><circle cx="280" cy="73" r="2.5"/><circle cx="365" cy="56" r="3"/></g>
                  <polygon points="270,14 408,54 270,94 132,54" className="map-outline"/>
                </g>
                <g className="isometric-input-layer input-layer-satellite">
                  <text x="20" y="124">SATELLITE</text><path className="map-leader" d="M91 120H126"/><circle cx="128" cy="120" r="2"/>
                  <polygon points="270,80 408,120 270,160 132,120" className="map-plane map-plane-satellite"/>
                  <g clipPath="url(#input-satellite)" className="map-detail map-detail-satellite"><path d="M125 108 177 91 222 108 194 132 142 134ZM220 92 270 101 282 124 237 141 200 123ZM286 101 337 88 391 108 364 135 307 130ZM153 136 203 125 241 151 183 158ZM292 139 345 127 384 145 331 159Z"/><path d="M156 91 349 149M184 82 372 137"/></g>
                  <polygon points="270,80 408,120 270,160 132,120" className="map-outline"/>
                </g>
                <g className="isometric-input-layer input-layer-elevation">
                  <text x="20" y="190">DSM / DTM</text><path className="map-leader" d="M98 186H126"/><circle cx="128" cy="186" r="2"/>
                  <polygon points="270,146 408,186 270,226 132,186" className="map-plane map-plane-elevation"/>
                  <g clipPath="url(#input-elevation)" className="map-detail map-detail-contours"><path d="M119 188C147 154 184 157 203 184S249 218 271 183 321 151 346 178 383 204 414 170M128 196C157 166 184 168 202 192S247 224 276 192 321 161 345 186 384 213 406 185M151 206C173 184 190 184 207 205S250 231 279 202 318 174 341 195 372 218 389 200M202 173C216 161 229 165 238 176M316 203C331 188 345 190 357 202"/></g>
                  <polygon points="270,146 408,186 270,226 132,186" className="map-outline"/>
                </g>
                <g className="isometric-input-layer input-layer-municipal">
                  <text x="20" y="256">MUNICIPAL</text><path className="map-leader" d="M101 252H126"/><circle cx="128" cy="252" r="2"/>
                  <polygon points="270,212 408,252 270,292 132,252" className="map-plane map-plane-municipal"/>
                  <g clipPath="url(#input-municipal)" className="map-detail map-detail-buildings"><path d="M158 247 181 238 198 246 176 256ZM205 263 230 252 248 261 224 273ZM251 239 275 232 291 240 269 250ZM295 258 320 247 337 255 312 267ZM343 239 365 233 382 241 360 250ZM178 271 198 264 215 272 195 281ZM272 273 292 265 309 274 289 284Z"/><path d="M148 259 205 281 251 259 307 281 386 247"/></g>
                  <polygon points="270,212 408,252 270,292 132,252" className="map-outline"/>
                </g>
                <g className="isometric-input-layer input-layer-utilities">
                  <text x="20" y="322">UTILITIES</text><path className="map-leader" d="M91 318H126"/><circle cx="128" cy="318" r="2"/>
                  <polygon points="270,278 408,318 270,358 132,318" className="map-plane map-plane-utilities"/>
                  <g clipPath="url(#input-utilities)" className="map-detail map-detail-utilities"><path className="utility-water" d="M126 319 173 303 211 313 243 335 287 337 323 321 366 300 411 312 411 342 363 332 319 350 275 353 230 341 192 326 153 337Z"/><path d="M150 315 193 302 230 318 271 301 315 315 350 299 390 317M178 285 193 302 190 346M250 282 230 318 237 352M335 284 315 315 325 346"/><circle cx="193" cy="302" r="3"/><circle cx="230" cy="318" r="3"/><circle cx="315" cy="315" r="3"/><circle cx="350" cy="299" r="3"/></g>
                  <polygon points="270,278 408,318 270,358 132,318" className="map-outline"/>
                </g>

                <path className="map-vertical-guide" d="M600 44V326"/>
                <text className="map-stage-label" x="600" y="28" textAnchor="middle">SPATIAL</text>
                <text className="map-stage-label" x="600" y="45" textAnchor="middle">PROCESSING</text>
                <g className="isometric-processing-layer"><polygon points="600,82 720,122 600,162 480,122" className="process-plane process-plane-top"/><g clipPath="url(#processing-top)" className="process-grid-lines"><path d="M480 122H720M510 112 630 152M540 102 660 142M570 92 690 132M510 132 630 92M540 142 660 102M570 152 690 112"/></g><polygon points="600,82 720,122 600,162 480,122" className="process-outline"/></g>
                <g className="isometric-processing-layer"><polygon points="600,126 720,166 600,206 480,166" className="process-plane process-plane-lower"/><g clipPath="url(#processing-middle)" className="process-detail"><path d="M500 166H700M530 150 650 190M550 180 670 140M570 146V186M615 151V181"/><rect x="594" y="161" width="7" height="7"/><rect x="635" y="168" width="6" height="6"/></g><polygon points="600,126 720,166 600,206 480,166" className="process-outline"/></g>
                <g className="isometric-processing-layer"><polygon points="600,170 720,210 600,250 480,210" className="process-plane process-plane-lower"/><g clipPath="url(#processing-lower)" className="process-detail"><path d="M500 210H700M530 194 650 234M550 224 670 184M570 190V230M615 195V225M660 200V220"/><rect x="578" y="204" width="7" height="7"/><rect x="627" y="211" width="6" height="6"/></g><polygon points="600,170 720,210 600,250 480,210" className="process-outline"/></g>
                <g className="isometric-processing-layer"><polygon points="600,214 720,254 600,294 480,254" className="process-plane process-plane-bottom"/><g clipPath="url(#processing-base)" className="process-detail process-detail-final"><path d="M500 254H700M530 238 650 278M550 268 670 228M570 234V274M615 239V269M660 244V264M540 254 570 264 600 254 630 264 660 254"/><rect x="594" y="249" width="7" height="7"/></g><polygon points="600,214 720,254 600,294 480,254" className="process-outline"/></g>

                <path className="map-flow-arrow" d="M428 190H478"/><path className="map-flow-head" d="m472 184 7 6-7 6"/><rect className="map-packet" x="440" y="185" width="6" height="6"/><rect className="map-packet" x="456" y="185" width="6" height="6"/><path className="map-coordinate-mark" d="M449 176v7m-4-3.5h8"/>
                <path className="map-flow-arrow map-flow-arrow-output" d="M731 190H770"/><path className="map-flow-head map-flow-head-output" d="m764 184 7 6-7 6"/><rect className="map-packet map-packet-output" x="741" y="185" width="6" height="6"/>

                <path className="map-vertical-guide" d="M880 54V102"/>
                <text className="map-stage-label" x="880" y="28" textAnchor="middle">ONE SPATIAL</text>
                <text className="map-stage-label" x="880" y="45" textAnchor="middle">INTELLIGENCE LAYER</text>
                <polygon points="880,106 1033,190 880,282 727,190" className="city-tile-shadow"/>
                <polygon points="880,98 1030,182 880,274 730,182" className="city-tile-face"/>
                <g clipPath="url(#city-map)" className="city-map-detail">
                  <path className="city-parcel-lines" d="M700 148 880 247 1060 148M744 125 921 225 1050 151M760 220 934 123M811 248 986 151M880 98V274M730 182H1030"/>
                  <path className="city-road-edge" d="M720 178 865 251 1040 154M790 102 980 218"/><path className="city-road" d="M720 178 865 251 1040 154M790 102 980 218"/>
                  <path className="city-park" d="M756 195 802 216 832 200 786 177ZM890 128 920 112 950 127 920 145Z"/>
                  <path className="city-water" d="M733 200 779 217 812 235 842 231 810 251 770 232 732 222Z"/>
                  <path className="city-buildings" d="m808 145 18-10 18 10-18 11Zm0 0v20l18 10v-19Zm18 11v19l18-10v-20Zm50-19 22-12 20 11-21 12Zm0 0v23l21 12v-24Zm21 12v24l21-13v-24Zm57 13 18-10 19 10-19 11Zm0 0v20l19 10v-20Zm19 10v20l19-10v-20Zm-125 58 19-10 20 10-20 12Zm0 0v21l20 11v-20Zm20 12v20l19-11v-21Zm105-42 22-12 20 11-21 12Zm0 0v23l21 12v-24Zm21 12v24l20-13v-23Z"/>
                  <path className="city-highlight-parcel" d="m889 160 21 11-20 12-21-12z"/>
                  <path className="city-coordinate-grid" d="M780 133 956 229M804 121 980 216M756 209 936 112M785 224 966 126"/>
                  <g className="city-tree-dots"><circle cx="779" cy="199" r="4"/><circle cx="800" cy="211" r="4"/><circle cx="928" cy="134" r="4"/><circle cx="953" cy="145" r="4"/><circle cx="965" cy="216" r="4"/></g>
                </g>
                <polygon points="880,98 1030,182 880,274 730,182" className="city-tile-outline"/>
                <g className="output-map-meta"><path className="north-arrow" d="m972 133 5 13-5-3-5 3z"/><text x="972" y="129" textAnchor="middle">N</text><path className="scale-rule" d="M820 250H902m-82-3v6m20-4v4m21-4v4m20-6v6m21-4v4"/><text x="820" y="264">0&nbsp;&nbsp; 100&nbsp;&nbsp; 200&nbsp;&nbsp; 400 m</text></g>
              </svg>
            </div>

            <div className="manifesto-steps">
              <article><span className="manifesto-step-number">01</span><div><h3>INPUT DATA</h3><p>Bring together diverse datasets across a city.</p></div></article>
              <article><span className="manifesto-step-number">02</span><div><h3>SPATIAL PROCESSING</h3><p>Align, harmonize and create a shared spatial reference.</p></div></article>
              <article><span className="manifesto-step-number">03</span><div><h3>OUTPUT</h3><p>A unified, trusted, actionable spatial intelligence layer.</p></div></article>
            </div>
          </div>
        </section>

        <section id="capabilities" className="section section-cream capabilities-section capability-editorial">
          <div className="container">
            <div className="capability-editorial-top"><SectionLabel number="03">Intelligence layer</SectionLabel><p>Every capability is designed to keep humans in control while making the work of reconciling spatial truth measurably clearer.</p></div>
            <div className="capability-editorial-heading"><h2>Six systems.<br /><em>One spatial</em><br /><em>workflow.</em></h2><span className="capability-heading-note">SPATIAL INTELLIGENCE<br />BUILT AROUND PEOPLE</span></div>
            <div className="capability-grid">
              {capabilities.slice(0, 3).map(({ n, title, desc, icon: Icon, crop }, index) => <Reveal key={title} delay={index * 50}><article className="capability-card"><div className="capability-card-top"><span>{n}</span><Icon size={18} strokeWidth={1.45} /></div><div className="capability-visual"><img src="/images/hero-aerial.webp" alt={`Aerial view illustrating ${title.toLowerCase()}`} style={{ objectPosition: crop }} /><span className="map-frame-mark" /></div><h3>{title}</h3><p>{desc}</p><span className="card-arrow" aria-hidden="true"><ArrowUpRight size={15} /></span></article></Reveal>)}
              <div className="capability-workflow" aria-label="Spatial workflow connecting all six capabilities">
                <span className="capability-workflow-label">SPATIAL WORKFLOW</span><span className="capability-workflow-start" />
                {["01", "02", "03"].map((step) => <span className="capability-milestone" key={step}>{step}</span>)}
                <span className="capability-workflow-end">CLEARER SPATIAL<br />TRUTH AHEAD <ArrowRight size={13} /></span>
              </div>
              {capabilities.slice(3).map(({ n, title, desc, icon: Icon, crop }, index) => <Reveal key={title} delay={(index + 3) * 50}><article className="capability-card"><div className="capability-card-top"><span>{n}</span><Icon size={18} strokeWidth={1.45} /></div><div className="capability-visual"><img src="/images/hero-aerial.webp" alt={`Aerial view illustrating ${title.toLowerCase()}`} style={{ objectPosition: crop }} /><span className="map-frame-mark" /></div><h3>{title}</h3><p>{desc}</p><span className="card-arrow" aria-hidden="true"><ArrowUpRight size={15} /></span></article></Reveal>)}
            </div>
          </div>
        </section>


        <section id="workflow" className="section section-cream workflow-section"><div className="container"><SectionLabel number="04">Workflow</SectionLabel><div className="section-heading-row"><Reveal><h2>From raw survey data<br /><em>to validated spatial intelligence.</em></h2></Reveal><Reveal delay={120}><p>A repeatable system for moving from raw files and field observations to a record that downstream teams can trust and use.</p></Reveal></div><div className="workflow-track"><div className="workflow-line"><span style={{ height: `${((activeWorkflow + 1) / workflow.length) * 100}%` }} /></div>{workflow.map(([number, title, desc], index) => <Reveal key={number} delay={index * 45}><button type="button" aria-pressed={index === activeWorkflow} onClick={() => setActiveWorkflow(index)} className={`workflow-step ${index === activeWorkflow ? "workflow-step-active" : ""}`}><span className="workflow-number">{number}</span><span className="workflow-content"><span className="workflow-top"><strong>{title}</strong>{index === activeWorkflow && <span className="live-chip"><i />Active step</span>}</span><span className="workflow-description">{desc}</span></span></button></Reveal>)}</div></div></section>

        <section id="gis" className="section section-dark gis-section"><div className="container"><SectionLabel number="05" light>Operational workspace</SectionLabel><div className="gis-intro"><Reveal><h2>A spatial truth you can <em>work with.</em></h2></Reveal><Reveal delay={120}><p>Monitor live parcel records, source data, quality and harmonization results from the existing project.</p></Reveal></div>

          <div className="dashboard-snapshot">
            {statsError && <div className="dashboard-api-error" role="status">Live project metrics could not be loaded: {statsError} <Link to="/system">Check system status <ArrowUpRight size={13} /></Link></div>}
            <div className="dashboard-metrics">{[
              ["Unified parcels", liveStats?.total_parcels], ["Buildings", liveStats?.total_buildings],
              ["Data sources", liveStats?.total_datasets], ["Matched features", liveStats?.matched_features],
              ["Open conflicts", liveStats?.open_conflicts], ["Average confidence", liveStats?.average_confidence, "%"],
              ["Topology issues", liveStats?.topology_errors], ["Detected changes", liveStats?.changes_detected],
            ].map(([label, value, suffix]) => <div className="dashboard-metric" key={label as string}><span>{label as string}</span><strong>{statsLoading ? "…" : value ?? "—"}{suffix as string || ""}</strong></div>)}</div>
            <div className="dashboard-charts">
              <article className="dashboard-chart"><h3>Feature distribution by source</h3><ResponsiveContainer width="100%" height={210}><BarChart data={distributionData} margin={{ top: 8, right: 8, bottom: 28, left: 0 }}><CartesianGrid strokeDasharray="3 3" stroke="#d6d0c3" vertical={false} /><XAxis dataKey="name" tick={{ fontSize: 9, fill: "#5e675d" }} angle={-24} textAnchor="end" interval={0} /><YAxis tick={{ fontSize: 9, fill: "#5e675d" }} /><Tooltip /><Bar dataKey="count" fill="#73866e" radius={[2, 2, 0, 0]} /></BarChart></ResponsiveContainer></article>
              <article className="dashboard-chart"><h3>Confidence distribution</h3><ResponsiveContainer width="100%" height={210}><PieChart><Pie data={confidenceData} dataKey="value" nameKey="name" cx="50%" cy="45%" outerRadius={68} label>{confidenceData.map((_, index) => <Cell key={index} fill={confidenceColors[index % confidenceColors.length]} />)}</Pie><Tooltip /><Legend wrapperStyle={{ fontSize: 10 }} /></PieChart></ResponsiveContainer></article>
              <article className="dashboard-chart"><h3>Conflict categories</h3><ResponsiveContainer width="100%" height={210}><BarChart data={conflictData} layout="vertical" margin={{ top: 6, right: 8, left: 12, bottom: 4 }}><CartesianGrid strokeDasharray="3 3" stroke="#d6d0c3" horizontal={false} /><XAxis type="number" tick={{ fontSize: 9, fill: "#5e675d" }} /><YAxis type="category" dataKey="name" width={105} tick={{ fontSize: 9, fill: "#5e675d" }} /><Tooltip /><Bar dataKey="value" fill="#a65e43" radius={[0, 2, 2, 0]} /></BarChart></ResponsiveContainer></article>
              <article className="dashboard-chart"><h3>Data quality by source</h3><ResponsiveContainer width="100%" height={210}><BarChart data={qualityData} margin={{ top: 8, right: 8, bottom: 28, left: 0 }}><CartesianGrid strokeDasharray="3 3" stroke="#d6d0c3" vertical={false} /><XAxis dataKey="name" tick={{ fontSize: 9, fill: "#5e675d" }} angle={-24} textAnchor="end" interval={0} /><YAxis domain={[0, 100]} tick={{ fontSize: 9, fill: "#5e675d" }} /><Tooltip /><Bar dataKey="score" fill="#a8b49a" radius={[2, 2, 0, 0]} /></BarChart></ResponsiveContainer></article>
            </div>
            <div className="dashboard-shortcuts"><Link to="/data-sources">Add data source <ArrowUpRight size={14} /></Link><Link to="/harmonization">Run harmonization <ArrowUpRight size={14} /></Link><Link to="/records">Browse land records <ArrowUpRight size={14} /></Link><Link to="/reports">Open reports <ArrowUpRight size={14} /></Link></div>
          </div>
          <div className="gis-shell"><aside className="gis-sidebar"><div className="gis-sidebar-head"><div><span className="eyebrow">LIVE PROJECT DATA</span><h3>Layers & sources</h3></div></div><div className="layer-list"><button className="layer-row" onClick={() => setShowParcelLayer((visible) => !visible)} aria-pressed={showParcelLayer}><span className={`layer-check ${showParcelLayer ? "is-on" : ""}`}>{showParcelLayer && <Check size={12} />}</span><span>Unified parcels</span><span className="layer-glyph">{liveParcels?.length ?? 0}</span></button></div><div className="gis-source-list"><span className="eyebrow">CONNECTED SOURCES</span>{(liveDatasets || []).slice(0, 8).map((dataset) => <div className="gis-source-row" key={dataset.id}><span>{displayDatasetName(dataset.name)}</span><small>{dataset.feature_count} features</small></div>)}{datasetsLoading && <small>Loading connected sources…</small>}{!datasetsLoading && (!liveDatasets || liveDatasets.length === 0) && <small>No data sources loaded.</small>}</div><div className="gis-sidebar-foot"><span>DATA HEALTH</span><strong><i className={statsError ? "is-offline" : ""} />{statsError ? "API unavailable" : statsLoading ? "Checking API…" : "Live project data"}</strong><small>{parcelsLoading ? "Loading parcel geometry…" : `${parcelFeatures.length} mappable parcel features`}</small></div></aside><div className="gis-map-wrap"><div className="map-toolbar"><span><Map size={15} /> Unified parcel map</span><Link to="/records">Open record table <ArrowUpRight size={13} /></Link></div><div className="map-stage"><MapView layers={mapLayers} onFeatureClick={handleMapFeatureClick} height="510px" showLayerControl={false} showLegend={false} /><div className="map-live-badge"><i />{parcelsLoading ? "Loading live records" : `${parcelFeatures.length} live parcel features`}</div></div><div className="map-footer"><span><span className="legend-dot dot-parcel" />Unified parcel boundaries</span><span className="map-live"><i /> Live data from BHUMI-X</span></div></div><aside className="parcel-panel"><div className="panel-top"><span className="eyebrow">Selected land record</span></div>{selectedParcel ? <><div className="parcel-id"><span>PARCEL ID</span><strong>{selectedParcel.parcel_id}</strong><small>{selectedParcel.owner_name || "Owner not recorded"}</small></div><div className="parcel-stats"><div><span>Area</span><strong>{selectedParcel.area ? `${selectedParcel.area.toLocaleString()} m²` : "—"}</strong></div><div><span>Sources</span><strong>{selectedParcel.source_count}</strong></div></div><div className="confidence-block"><div className="confidence-head"><span>Confidence profile</span><span className="confidence-good">{selectedParcel.confidence_score.toFixed(0)}%</span></div>{[["Spatial", selectedParcel.spatial_confidence], ["Attributes", selectedParcel.attribute_confidence], ["Geometry", selectedParcel.geometry_confidence]].map(([label, score]) => <div className="confidence-row" key={label as string}><span>{label as string}</span><div className="confidence-bar"><i style={{ width: `${score as number}%` }} /></div><strong>{(score as number).toFixed(0)}%</strong></div>)}</div><div className="validation-list"><div><span>Validation</span><strong>{selectedParcel.validation_status}</strong></div><div><span>Conflicts</span><strong>{selectedParcel.conflict_status}</strong></div><div><span>Buildings</span><strong>{selectedParcel.building_count}</strong></div><div><span>Utilities</span><strong>{selectedParcel.utility_count}</strong></div><div><span>GNSS evidence</span><strong>{Object.entries(selectedParcel.lineage || {}).some(([type, source]) => type.toLowerCase().includes("gnss") && source.provenance === "synthetic_demo") ? "Linked" : selectedParcel.gnss_verified ? "Linked" : "None"}</strong></div></div><div className="parcel-actions"><Link className="button button-dark-outline" to="/conflicts"><Eye size={15} /> Review conflicts</Link><Link className="button button-clay" to="/records">Open record <ArrowUpRight size={15} /></Link></div></> : <div className="parcel-empty">{parcelsLoading ? "Loading project parcels…" : liveParcels?.length ? "Select a parcel on the map to view its attributes and confidence." : "No live parcel geometry is available yet. Upload datasets and run harmonization."}</div>}</aside></div></div></section>


        <section id="comparison" className="section section-cream comparison-section"><div className="container"><SectionLabel number="06">Before / after</SectionLabel><div className="comparison-heading"><Reveal><h2>Same city.<br /><em>Different level of clarity.</em></h2></Reveal><Reveal delay={100}><p>Drag the divider to move from disconnected overlays to a harmonized record with provenance, validation and confidence built in.</p></Reveal></div><div className="comparison-frame"><div className="comparison-before"><div className="comparison-art before-art"><div className="ghost-layers"><span /><span /><span /><span /><span /></div><div className="messy-label">MANUAL GIS OVERLAY</div></div><div className="comparison-copy"><span>Before / 00</span><h3>Disconnected datasets</h3><ul><li>Different coordinate systems</li><li>Duplicate records</li><li>Conflicting boundaries</li><li>Slow validation</li></ul></div></div><div className="comparison-after"><div className="comparison-art after-art"><div className="aligned-parcels"><span /><span /><span /><span /><span /></div><div className="clean-label"><CircleCheck size={14} /> HARMONIZED</div></div><div className="comparison-copy"><span>After / 01</span><h3>Harmonized land intelligence</h3><ul><li>Unified spatial reference</li><li>AI feature matching</li><li>Topology validation</li><li>Confidence scoring</li></ul></div></div><div className="comparison-divider" style={{ left: `${beforeAfter}%` }}><button aria-label="Drag comparison slider" onKeyDown={(event) => { if (event.key === "ArrowLeft") setBeforeAfter((v) => Math.max(10, v - 5)); if (event.key === "ArrowRight") setBeforeAfter((v) => Math.min(90, v + 5)); }}><ArrowRight size={16} /></button></div><input className="comparison-range" type="range" min="10" max="90" value={beforeAfter} onChange={(event) => setBeforeAfter(Number(event.target.value))} aria-label="Before and after comparison" /></div></div></section>

        <section id="architecture" className="section architecture-section">
          <div className="container architecture-editorial">
            <div className="architecture-copy">
              <div className="architecture-eyebrow"><span>07</span><i /><span>ARCHITECTURE</span></div>
              <Reveal>
                <h2>Built as a spatial<br /><em>intelligence pipeline.</em></h2>
              </Reveal>
              <div className="architecture-highlight" />
              <Reveal delay={100}>
                <p>A modular technical foundation for connecting field observations, source systems and the interfaces that operational teams already use.</p>
              </Reveal>
              <svg className="architecture-terrain" viewBox="0 0 520 270" aria-hidden="true" focusable="false">
                <path className="terrain-layer terrain-back" d="M18 165 132 83 236 114 337 45 502 102 447 205 286 222 165 196 58 220Z" />
                <path className="terrain-layer terrain-mid" d="M18 184 132 102 236 133 337 64 502 121 447 224 286 241 165 215 58 239Z" />
                <path className="terrain-layer terrain-front" d="M18 203 132 121 236 152 337 83 502 140 447 243 286 260 165 234 58 258Z" />
                <path className="terrain-contour" d="M51 178 135 119 235 149 336 82 469 130M85 205 157 155 236 176 333 116 440 153M127 225 179 188 244 204 326 151 409 176" />
                <path className="terrain-link" d="M144 128 223 176 337 91 412 159" />
                <circle cx="144" cy="128" r="4" /><circle cx="223" cy="176" r="4" /><circle cx="337" cy="91" r="4" /><circle cx="412" cy="159" r="4" />
              </svg>
            </div>

            <div className="architecture-flow-wrap">
              <ol className="architecture-timeline" aria-label="Architecture pipeline stages">
                {architecture.map((step) => (
                  <li key={step.number} className={step.number === activeArchitecture ? "is-active" : ""} aria-current={step.number === activeArchitecture ? "step" : undefined}>
                    <span>{step.number}</span>
                  </li>
                ))}
              </ol>
              <div className="architecture-pipeline">
                <svg className="architecture-connectors" viewBox="0 0 1000 700" preserveAspectRatio="none" aria-hidden="true" focusable="false">
                  <path d="M166 80H500H834V250H500H166V420H500H834V590H500" />
                </svg>
                <div className="architecture-card-grid">
                  {architecture.map((step, index) => {
                    const Icon = step.icon
                    return (
                      <article
                        key={step.number}
                        className={`architecture-card${step.number === activeArchitecture ? " is-active" : ""}${index === 9 ? " is-wide" : ""}`}
                        onMouseEnter={() => setActiveArchitecture(step.number)}
                        onMouseLeave={() => setActiveArchitecture("04")}
                        onFocus={() => setActiveArchitecture(step.number)}
                        onBlur={(event) => {
                          if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setActiveArchitecture("04");
                        }}
                      >
                        <div className="architecture-card-top">
                          <span className="architecture-icon"><Icon size={17} strokeWidth={1.7} /></span>
                          <span className="architecture-card-number">{step.number}</span>
                        </div>
                        <h3>{step.title}</h3>
                        <p>{step.description}</p>
                        <Link className="architecture-card-link" to={step.href} aria-label={step.action}>
                          <ArrowRight size={14} />
                        </Link>
                      </article>
                    )
                  })}
                </div>
              </div>
            </div>
          </div>
        </section>

        <section id="use-cases" className="section section-cream use-cases-section"><div className="container"><SectionLabel number="08">Use cases</SectionLabel><div className="use-cases-heading"><Reveal><h2>One intelligence layer.<br /><em>Many public missions.</em></h2></Reveal><Reveal delay={100}><p>Designed for the people who steward the spatial record — from survey teams and municipal GIS units to data and planning departments.</p></Reveal></div><div className="use-cases-grid">{useCases.map(([title, desc, Icon], index) => <Reveal key={title as string} delay={index * 45}><article className="use-case-card"><div className="use-case-icon"><Icon size={20} /></div><span>{String(index + 1).padStart(2, "0")}</span><h3>{title as string}</h3><p>{desc as string}</p><ArrowUpRight size={17} /></article></Reveal>)}</div></div></section>

        <section id="interoperability" className="section section-dark interop-section"><div className="container"><SectionLabel number="09" light>Government / interoperability</SectionLabel><div className="interop-grid"><Reveal><h2>Designed for the way public geospatial data <em>actually works.</em></h2></Reveal><div className="interop-list">{["Department-to-department interoperability", "Standardized spatial schemas", "API-first architecture", "Spatial database integration", "GIS export / import", "Auditability", "Human-in-the-loop validation", "Role-based access", "Data provenance"].map((item) => <Reveal key={item}><div><Check size={15} />{item}</div></Reveal>)}</div></div><div className="interop-footnote"><span>BHUMI-X / POSITION</span><p>Designed to support workflows aligned with modern digital land governance initiatives — without claiming official approval, endorsement or deployment.</p></div></div></section>


      </div>

      <footer className="site-footer"><div className="container"><div className="footer-top"><div className="footer-brand"><a className="brand" href="#hero"><span className="brand-mark"><span /><span /><span /></span><span>BHUMI-X</span></a><p>Intelligent spatial harmonization<br />for urban land records.</p></div><div className="footer-column"><h4>Platform</h4><a href="#capabilities">Capabilities</a><a href="#workflow">Workflow</a><a href="#gis">GIS demo</a><a href="#architecture">Architecture</a></div><div className="footer-column"><h4>Technology</h4><a href="#architecture">AI / ML</a><a href="#architecture">Computer vision</a><a href="#architecture">PostGIS</a><a href="#architecture">Spatial ETL</a></div><div className="footer-column"><h4>Project</h4><a href="#challenge">Problem statement</a><a href="#idea">Solution</a><a href="#use-cases">Use cases</a><a href="#interoperability">Documentation</a></div><div className="footer-column"><h4>Connect</h4><a href="mailto:hello@bhumi.ai">Email <ArrowUpRight size={13} /></a><Link to="/data-sources">Data sources <ArrowUpRight size={13} /></Link></div></div><div className="footer-bottom"><span>© 2026 BHUMI-X</span><span>Built for a more coherent spatial future <span className="footer-line" /></span><span>AI / GIS / CIVIC INFRASTRUCTURE</span></div></div></footer>
      <button className={`section-pip ${activeSection !== "hero" ? "pip-visible" : ""}`} onClick={() => scrollToId(`#${activeSection}`)} aria-label="Return to current section"><span /><small>{activeSection.replace("-", " / ")}</small></button>
    </div>
  );
}
