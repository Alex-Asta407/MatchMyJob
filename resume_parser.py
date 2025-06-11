"""
resume_parser.py

A modern resume parser that extracts skills, education, and experience
from resumes in PDF and DOCX formats.
"""
import re
import json
from typing import List, Dict, Optional, Union, Any
from dataclasses import dataclass
from pathlib import Path
import pdfplumber
import logging
from utils import normalize_skill

# PDF extraction
from pdfminer.high_level import extract_text as extract_pdf_text
from pdfminer.pdfparser import PDFSyntaxError
from PyPDF2 import PdfReader
from pdf2image import convert_from_path

# OCR
import pytesseract

# DOCX extraction
from docx import Document as DocxDocument

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class Education:
    degree: str
    institution: str
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    gpa: Optional[float] = None
    description: Optional[List[str]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            'degree': self.degree,
            'institution': self.institution,
            'start_date': self.start_date,
            'end_date': self.end_date,
            'gpa': self.gpa,
            'description': self.description
        }

@dataclass
class Experience:
    title: str
    company: str
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    description: Optional[List[str]] = None
    achievements: Optional[List[str]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            'title': self.title,
            'company': self.company,
            'start_date': self.start_date,
            'end_date': self.end_date,
            'description': self.description,
            'achievements': self.achievements
        }

@dataclass
class ParsedResume:
    raw_text: str
    skills: List[str]
    education: List[Education]
    experience: List[Experience]

    def to_dict(self) -> Dict[str, Any]:
        return {
            'raw_text': self.raw_text,
            'skills': self.skills,
            'education': [edu.to_dict() for edu in self.education],
            'experience': [exp.to_dict() for exp in self.experience]
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

class ResumeParser:
    """
    A modern resume parser that extracts structured information from resumes.
    """
    
    # Common date patterns
    DATE_PATTERNS = [
        r'(?P<month>Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s*(?P<year>\d{4})',
        r'(?P<year>\d{4})',
        r'(?P<month>\d{1,2})/(?P<year>\d{4})',
        r'(?P<month>\d{1,2})-(?P<year>\d{4})',
        r'(?P<month>Sep|Feb|Jan|Mar|Apr|May|Jun|Jul|Aug|Oct|Nov|Dec)\s*(?P<year>\d{4})\s*—\s*(?:Present|(?P<end_month>Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s*(?P<end_year>\d{4}))',
    ]

    # Common section headers
    SECTION_HEADERS = {
        'skills': [
            r'^[\s_\-]*skills[\s_\-:]*$',
            r'^[\s_\-]*technical\s+skills[\s_\-:]*$',
            r'^[\s_\-]*core\s+competencies[\s_\-:]*$',
            r'^[\s_\-]*expertise[\s_\-:]*$',
            r'^[\s_\-]*S\s+K\s+I\s+L\s+L\s+S[\s_\-:]*$',
            r'^[\s_\-]*T\s+E\s+C\s+H\s+N\s+I\s+C\s+A\s+L\s+\s+S\s+K\s+I\s+L\s+L\s+S[\s_\-:]*$',
            r'^[\s_\-]*TECHNICAL\s+SKILLS[\s_\-:]*$',
            r'^[\s_\-]*SKILLS[\s_\-:]*$',
            r'^[\s_\-]*Skills[\s_\-:]*$',
            r'^[\s_\-]*Technical\s+Skills[\s_\-:]*$',
            r'^[\s_\-]*Core\s+Competencies[\s_\-:]*$',
            r'^[\s_\-]*Expertise[\s_\-:]*$',
            r'^[\s_\-]*Professional\s+Skills[\s_\-:]*$',
            r'^[\s_\-]*Key\s+Skills[\s_\-:]*$',
            r'^[\s_\-]*Technical\s+Expertise[\s_\-:]*$',
            r'^[\s_\-]*Programming\s+Skills[\s_\-:]*$',
            r'^[\s_\-]*Development\s+Skills[\s_\-:]*$',
            r'^[\s_\-]*Software\s+Skills[\s_\-:]*$',
            r'^[\s_\-]*IT\s+Skills[\s_\-:]*$',
            r'^[\s_\-]*Computer\s+Skills[\s_\-:]*$',
            r'^[\s_\-]*Computer\s+Proficiency[\s_\-:]*$',
            r'^[\s_\-]*Software\s+Proficiency[\s_\-:]*$',
            r'^[\s_\-]*Software\s+Knowledge[\s_\-:]*$',
            r'^[\s_\-]*Computer\s+Knowledge[\s_\-:]*$',
            r'^[\s_\-]*Computer\s+Literacy[\s_\-:]*$',
        ],
        'education': [
            r'^[\s_\-]*education[\s_\-:]*$',
            r'^[\s_\-]*academic\s+background[\s_\-:]*$',
            r'^[\s_\-]*academic\s+qualifications[\s_\-:]*$',
            r'^[\s_\-]*E\s*D\s*U\s*C\s*A\s*T\s*I\s*O\s*N[\s_\-:]*$',
            r'^[\s_\-]*E\s+D\s+U\s+C\s+A\s+T\s+I\s+O\s+N[\s_\-:]*$',
            r'^[\s_\-]*A\s+C\s+A\s+D\s+E\s+M\s+I\s+C\s+\s+B\s+A\s+C\s+K\s+G\s+R\s+O\s+U\s+N\s+D[\s_\-:]*$',
            r'^[\s_\-]*EDUCATION[\s_\-:]*$',
            r'^[\s_\-]*Education[\s_\-:]*$',
            r'^[\s_\-]*EDUC AT ION[\s_\-:]*$',
            r'^[\s_\-]*Academic\s+Background[\s_\-:]*$',
            r'^[\s_\-]*Academic\s+Qualifications[\s_\-:]*$',
            r'^[\s_\-]*Continuing\s+Education[\s_\-:]*$',
            r'^[\s_\-]*Continuing\s+Studies[\s_\-:]*$',
        ],
        'experience': [
            r'^[\s_\-]*experience[\s_\-:]*$',
            r'^[\s_\-]*employment\s+history[\s_\-:]*$',
            r'^[\s_\-]*work\s+experience[\s_\-:]*$',
            r'^[\s_\-]*E\s+X\s+P\s+E\s+R\s+I\s+E\s+N\s+C\s+E[\s_\-:]*$',
            r'^[\s_\-]*E\s+M\s+P\s+L\s+O\s+Y\s+M\s+E\s+N\s+T\s+\s+H\s+I\s+S\s+T\s+O\s+R\s+Y[\s_\-:]*$',
            r'^[\s_\-]*EXPERIENCE[\s_\-:]*$',
            r'^[\s_\-]*Experience[\s_\-:]*$',
            r'^[\s_\-]*Employment\s+History[\s_\-:]*$',
            r'^[\s_\-]*Work\s+Experience[\s_\-:]*$',
            r'^[\s_\-]*Professional\s+Experience[\s_\-:]*$',
            r'^[\s_\-]*Work\s+History[\s_\-:]*$',
            r'^[\s_\-]*Career\s+History[\s_\-:]*$',
            r'^[\s_\-]*Job\s+History[\s_\-:]*$',
            r'^[\s_\-]*Positions\s+Held[\s_\-:]*$',
            r'^[\s_\-]*Career\s+Experience[\s_\-:]*$',
            r'^[\s_\-]*Work\s+Background[\s_\-:]*$',
            r'^[\s_\-]*Employment\s+Background[\s_\-:]*$',
        ],
        'profile': [
            r'^[\s_\-]*profile[\s_\-:]*$',
            r'^[\s_\-]*summary[\s_\-:]*$',
            r'^[\s_\-]*P\s+R\s+O\s+F\s+I\s+L\s+E[\s_\-:]*$',
            r'^[\s_\-]*S\s+U\s+M\s+M\s+A\s+R\s+Y[\s_\-:]*$',
            r'^[\s_\-]*PROFILE[\s_\-:]*$',
            r'^[\s_\-]*Profile[\s_\-:]*$',
            r'^[\s_\-]*SUMMARY[\s_\-:]*$',
            r'^[\s_\-]*Summary[\s_\-:]*$',
            r'^[\s_\-]*Professional\s+Summary[\s_\-:]*$',
            r'^[\s_\-]*Career\s+Summary[\s_\-:]*$'
        ]
    }

    # Common degree patterns
    DEGREE_PATTERNS = [
        r'(?i)(Bachelor|Master|PhD|Doctor|B\.?S\.?|M\.?S\.?|B\.?A\.?|M\.?A\.?|B\.?E\.?|M\.?E\.?)',
        r'(?i)(Associate|Diploma|Certificate)',
        r'(?i)(Computer Science|Engineering|Business|Arts|Science|Information Systems|Cybersecurity)',
    ]

    # Common job title patterns
    JOB_TITLE_PATTERNS = [
        r'(?i)(Senior|Lead|Principal|Staff|Junior|Associate)?\s*(Software|Frontend|Backend|Full[- ]Stack|DevOps|Data|Machine Learning|AI|Cloud|Security|QA|Test|Product|Project|Business|System|Network|Database|Mobile|Web|UI|UX|Design|Architect|Engineer|Developer|Analyst|Scientist|Consultant|Manager|Director|Head|Chief|Officer|Administrator|Specialist|Coordinator|Assistant|Intern)',
    ]

    def __init__(self):
        self.raw_text = ""
        self.section_patterns = {
            section: [re.compile(p, re.MULTILINE|re.IGNORECASE) for p in patterns]
            for section, patterns in self.SECTION_HEADERS.items()
        }
        self.date_patterns = [re.compile(pattern) for pattern in self.DATE_PATTERNS]
        self.degree_patterns = [re.compile(pattern) for pattern in self.DEGREE_PATTERNS]
        self.job_title_patterns = [re.compile(pattern) for pattern in self.JOB_TITLE_PATTERNS]


    def _extract_text(self, filepath: Union[str, Path]) -> str:
        """Extract text from PDF or DOCX file, with pdfplumber fallback for PDFs."""
        try:
            filepath = Path(filepath)
            if not filepath.exists():
                raise FileNotFoundError(f"File not found: {filepath}")
            if filepath.suffix.lower() == '.pdf':
                try:
                    # First try normal text extraction
                    text = extract_pdf_text(str(filepath))
                    # If no text was extracted, try OCR
                    if not text or len(text.strip()) == 0:
                        logger.info(f"No text extracted normally, trying OCR for {filepath}")
                        text = self._extract_text_with_ocr(filepath)
                    if not text or len(text.strip()) == 0:
                        logger.warning(f"Warning: Both normal extraction and OCR returned empty text for {filepath}")
                    # Try pdfplumber as a fallback or for debugging
                    try:
                        with pdfplumber.open(str(filepath)) as pdf:
                            plumber_text = "\n".join(page.extract_text() or '' for page in pdf.pages)
                        logger.info("\nPDFPLUMBER EXTRACTED TEXT (first 2000 chars):\n" + plumber_text[:2000])
                        # If plumber_text is longer or has more lines than the default, use it
                        if plumber_text and (not text or len(plumber_text.splitlines()) > len(text.splitlines())):
                            logger.info("Using pdfplumber text extraction as it appears more complete.")
                            text = plumber_text
                    except Exception as e:
                        logger.warning(f"pdfplumber extraction failed: {e}")
                    return text
                except PDFSyntaxError as e:
                    logger.warning(f"PDF syntax error, trying OCR: {str(e)}")
                    return self._extract_text_with_ocr(filepath)
                except Exception as e:
                    logger.error(f"Error extracting text from PDF {filepath}: {str(e)}")
                    raise
            elif filepath.suffix.lower() == '.docx':
                try:
                    doc = DocxDocument(str(filepath))
                    text = '\n'.join(paragraph.text for paragraph in doc.paragraphs)
                    if not text or len(text.strip()) == 0:
                        logger.warning(f"Warning: DOCX text extraction returned empty text for {filepath}")
                    return text
                except Exception as e:
                    logger.error(f"Error extracting text from DOCX {filepath}: {str(e)}")
                    raise
            else:
                raise ValueError(f"Unsupported file type: {filepath.suffix}")
        except Exception as e:
            logger.error(f"Error in text extraction: {str(e)}")
            raise

    def _preprocess_text(self, text: str) -> str:
        """Clean and normalize the text."""
        # normalize DOS/Mac line endings
        text = text.replace('\r\n', '\n').replace('\r', '\n')

        # Remove lines that are just underscores, dashes, or similar
        text = re.sub(r'^[\s_\-]{3,}$', '', text, flags=re.MULTILINE)

        # Collapse spaced-out uppercase headings
        def _collapse_spaced_header(match):
            return match.group(0).replace(' ', '')
        text = re.sub(
            r'\b(?:[A-Z]\s+){2,}[A-Z]\b',
            _collapse_spaced_header,
            text
        )

        # clean up PDF garbage, bullets, dashes
        text = re.sub(r'\(cid:\d+\)', '•', text)
        text = re.sub(r'[•●○◆◇■□▪▫]', '•', text)
        text = re.sub(r'[–—]', '-', text)

        # strip out long underline runs after headers
        text = re.sub(r'([A-Za-z ]+)\s*_{3,}', r'\1', text)

        # collapse multiple blank lines to *two* newlines
        text = re.sub(r'\n\s*\n+', '\n\n', text)

        # Only replace tabs with a single space (do not collapse all spaces)
        text = re.sub(r'\t+', ' ', text)

        # Remove special characters but keep basic punctuation and additional characters needed for education
        text = re.sub(r'[^\w\s\.,;:\-•()&\+\/]', '', text)

        return text.strip()

    def _extract_sections(self, text: str) -> Dict[str, str]:
        """
        Split resume text into named sections by detecting lines that begin
        with section keywords (Skills, etc.). Only used for skills.
        """
        import re
        header_map = {
            'skills': [
                'skills', 'technical skills', 'core competencies', 'expertise', 'professional skills', 'key skills',
                'technical expertise', 'programming skills', 'development skills', 'software skills', 'it skills', 'computer skills',
                'computer proficiency', 'software proficiency', 'software knowledge', 'computer knowledge', 'computer literacy'
            ],
        }
        sections: Dict[str, str] = {}
        current: Optional[str] = None
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            low = stripped.lower()
            header_hit = False
            for sec, keys in header_map.items():
                for kw in keys:
                    if re.match(rf'^{re.escape(kw)}\b', low):
                        current = sec
                        sections.setdefault(sec, '')
                        rest = re.sub(rf'^{re.escape(kw)}[\s\-:]*', '', stripped, flags=re.IGNORECASE)
                        if rest:
                            sections[sec] += rest + '\n'
                        header_hit = True
                        break
                if header_hit:
                    break
            if header_hit:
                continue
            if current:
                sections[current] += stripped + '\n'
        # Debug: print detected skills section
        if 'skills' in sections:
            logger.info(f"[DEBUG] Detected skills section:\n{sections['skills']}")
        return {s: b.strip() for s, b in sections.items() if b.strip()}

    def _extract_sections_old(self, text: str) -> Dict[str, str]:
        """Old section splitter using SECTION_HEADERS regex patterns. Used for education and experience, and fallback for skills."""
        import re
        lines = text.split('\n')
        section_indices = []
        for i, line in enumerate(lines):
            for section, patterns in self.SECTION_HEADERS.items():
                for pattern in patterns:
                    if re.match(pattern, line.strip(), re.IGNORECASE):
                        section_indices.append((i, section))
        section_indices.append((len(lines), None))  # sentinel
        sections = {}
        for idx in range(len(section_indices) - 1):
            start, section = section_indices[idx]
            end, _ = section_indices[idx + 1]
            if section:
                content = '\n'.join(lines[start + 1:end]).strip()
                if content:
                    sections[section] = content
        # Debug: print detected experience section
        if 'experience' in sections:
            logger.info(f"[DEBUG] Detected experience section:\n{sections['experience']}")
        # Debug: print detected skills section (fallback)
        if 'skills' in sections:
            logger.info(f"[DEBUG] (Fallback) Detected skills section:\n{sections['skills']}")
        return sections

    def _is_gpa_or_language(self, text: str) -> bool:
        """Check if text is a GPA or language entry."""
        # Check for GPA patterns
        gpa_patterns = [
            r'^GPA:\s*\d+(?:\.\d+)?$',
            r'^GPA:\s*\d+(?:\.\d+)?/\d+$',
            r'^\d+(?:\.\d+)?/\d+\s*$',  # Matches patterns like "9.33/10"
            r'^\d+/\d+\s*$'  # Matches patterns like "91/100"
        ]

        return any(re.match(pattern, text, re.IGNORECASE) for pattern in gpa_patterns)

    def _parse_skills(self, text: str, raw_text: str) -> List[str]:
        if not text:
            return []
        has_experience_section = bool(re.search(r'(?im)^\s*(experience|employment history|work experience)\s*[:\-]?', raw_text))
        # List of common language names and proficiency levels
        language_keywords = set([
            'english', 'french', 'russian', 'ukrainian', 'german', 'spanish', 'italian', 'portuguese', 'polish', 'chinese', 'japanese', 'native speaker', 'native', 'bilingual', 'multilingual', 'arabic', 'turkish', 'czech', 'slovak', 'estonian', 'latvian', 'lithuanian', 'romanian', 'bulgarian', 'hungarian', 'greek', 'serbian', 'croatian', 'slovenian', 'dutch', 'swedish', 'norwegian', 'finnish', 'danish', 'hebrew', 'hindi', 'vietnamese', 'thai', 'indonesian', 'malay', 'filipino', 'korean', 'mandarin', 'cantonese', 'fluent', 'proficient', 'basic', 'intermediate', 'advanced', 'elementary', 'native'
        ])
        proficiency_pattern = re.compile(r'^(a1|a2|b1|b2|c1|c2)\b', re.IGNORECASE)
        # Normalize bullets/semicolons to commas, then split
        normalized = text.replace('•', ',').replace(';', ',')
        # Flatten multi-column rows first (your existing logic)
        lines = []
        for raw_line in normalized.split('\n'):
            if re.search(r'\S\s{2,}\S', raw_line):
                parts = re.split(r'\s{2,}', raw_line)
                if all(len(p.split()) <= 4 for p in parts):
                    lines.extend(p.strip() for p in parts)
                    continue
            lines.append(raw_line.strip())

        # Now split on commas and/or newlines
        items = []
        for line in lines:
            for part in re.split(r'[\,\n]', line):
                part = part.strip()
                # Skip section headers like 'Experience:' or 'Experience'
                if re.match(r'^(experience|experience:)$', part.strip().lower()):
                    continue
                # If experience section exists, skip lines that start with a dash or bullet (likely experience/achievement lines)
                if has_experience_section and re.match(r'^[-•]', part):
                    continue
                # Skip items that look like experience/job entries
                if (
                    re.search(r'\b\d{4}\b', part) or  # contains a year
                    re.search(r'\b(at|intern|engineer|manager|developer|analyst|consultant|corp|inc|llc|ltd)\b', part, re.IGNORECASE) or
                    any(p.search(part) for p in self.job_title_patterns)
                ):
                    continue
                # Skip language names and proficiency levels
                if part.lower() in language_keywords or proficiency_pattern.match(part):
                    continue
                if part and not re.match(r'^gpa\b', part, re.IGNORECASE):
                    items.append(part)

        # Dedupe & return
        seen = set()
        skills = []
        for s in items:
            key = s.lower()
            if key not in seen:
                seen.add(key)
                skills.append(s)
        return skills

    def _parse_education(self, text: str) -> List[Education]:
        """Parse education information from the education section, supporting both date-first and school-first formats."""
        education_entries = []
        if not text:
            return education_entries
        lines = text.split('\n')
        current_entry = None
        current_description = []
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            if not line:
                i += 1
                continue
            # Skip section headers
            section_header_keywords = [
                'education', 'skills', 'experience', 'profile', 'summary', 'languages',
                'academic', 'employment', 'work', 'projects', 'certifications', 'leadership'
            ]
            if any(k in line.lower().replace(' ', '') for k in section_header_keywords):
                i += 1
                continue
            # Skip GPA/Language lines
            if self._is_gpa_or_language(line):
                i += 1
                continue
            dates = self._extract_dates(line)
            # --- DATE-FIRST LOGIC ---
            if dates:
                # Save previous entry
                if current_entry:
                    if current_description:
                        current_entry.description = current_description
                    education_entries.append(current_entry)
                    current_description = []
                # Start new entry
                current_entry = Education(
                    degree='',
                    institution='',
                    start_date=dates[0],
                    end_date=(dates[1] if len(dates) > 1 else None),
                    gpa=None,
                    description=[]
                )
                # Next line: degree/institution
                if i+1 < len(lines):
                    next_line = lines[i+1].strip()
                    if ',' in next_line:
                        parts = [p.strip() for p in next_line.split(',', 1)]
                        current_entry.degree = parts[0]
                        current_entry.institution = parts[1] if len(parts) > 1 else ''
                    else:
                        current_entry.degree = next_line
                    i += 1
                # Next line: location (optional, not a bullet or empty)
                if i+1 < len(lines):
                    possible_loc = lines[i+1].strip()
                    if possible_loc and not possible_loc.startswith('•') and not self._extract_dates(possible_loc):
                        if current_entry.institution:
                            current_entry.institution += ' ' + possible_loc
                        else:
                            current_entry.institution = possible_loc
                        i += 1
            # --- SCHOOL-FIRST LOGIC ---
            elif (',' in line or 'university' in line.lower() or 'college' in line.lower() or 'school' in line.lower()) and not line.startswith('•'):
                # Save previous entry
                if current_entry:
                    if current_description:
                        current_entry.description = current_description
                    education_entries.append(current_entry)
                    current_description = []
                # Start new entry
                # Try to split institution and location
                institution = line
                location = ''
                date_str = ''
                # If there are two columns (e.g., institution left, location right)
                if '\t' in line:
                    parts = [p.strip() for p in line.split('\t')]
                    institution = parts[0]
                    if len(parts) > 1:
                        location = parts[1]
                elif ',' in line:
                    # Try to split last comma as location
                    parts = [p.strip() for p in line.rsplit(',', 1)]
                    institution = parts[0]
                    if len(parts) > 1:
                        location = parts[1]
                current_entry = Education(
                    degree='',
                    institution=institution + (f', {location}' if location else ''),
                    start_date=None,
                    end_date=None,
                    gpa=None,
                    description=[]
                )
                # Next line: degree (if not empty or bullet)
                if i+1 < len(lines):
                    next_line = lines[i+1].strip()
                    if next_line and not next_line.startswith('•') and not self._extract_dates(next_line):
                        current_entry.degree = next_line
                        i += 1
                # Next line: date (if looks like a date or month/year)
                if i+1 < len(lines):
                    possible_date = lines[i+1].strip()
                    possible_dates = self._extract_dates(possible_date)
                    if possible_dates:
                        if not current_entry.start_date:
                            current_entry.start_date = possible_dates[0]
                        if len(possible_dates) > 1:
                            current_entry.end_date = possible_dates[1]
                        i += 1
            elif current_entry:
                if line.startswith('•'):
                    current_description.append(line.lstrip('•- ').strip())
                elif 'gpa' in line.lower():
                    gpa_match = re.search(r'(\d+(?:\.\d+)?)/\d+', line)
                    if gpa_match:
                        current_entry.gpa = float(gpa_match.group(1))
                    else:
                        # Try to extract GPA like 'GPA: 3.7 Magna Cum Laude'
                        gpa_match2 = re.search(r'gpa[:\s]+([0-9.]+)', line, re.IGNORECASE)
                        if gpa_match2:
                            current_entry.gpa = float(gpa_match2.group(1))
                        current_description.append(line)
                else:
                    current_description.append(line)
            i += 1
        # Add last entry
        if current_entry:
            if current_description:
                current_entry.description = current_description
            education_entries.append(current_entry)
        # Clean up: Only keep entries with degree or institution
        cleaned_entries = []
        for entry in education_entries:
            if entry.degree or entry.institution:
                cleaned_entries.append(entry)
        return cleaned_entries

    def _parse_experience(self, text: str) -> List[Experience]:
        """Parse experience entries from the experience section (restored old logic, now with contact info filtering)."""
        if not text:
            return []
        experience_entries = []
        current_entry = None
        section_header_keywords = [
            'education', 'skills', 'experience', 'profile', 'summary', 'languages',
            'academic', 'employment', 'work', 'projects', 'certifications', 'leadership'
        ]
        contact_patterns = [
            re.compile(r'\b\+?\d{7,}\b'),  # phone numbers
            re.compile(r'@'),                 # emails
            re.compile(r'\b(lithuania|ukraine|usa|united states|germany|france|poland|india|canada|england|spain|italy|netherlands|sweden|norway|finland|estonia|latvia|lithuania|russia|belarus|kazakhstan|uzbekistan|turkey|china|japan|korea|brazil|mexico|argentina|australia|new zealand)\b', re.IGNORECASE),
        ]
        
        # Filter out skill-related lines first
        filtered_lines = []
        for line in text.split('\n'):
            line = line.strip()
            if not line:
                continue
            # Skip skill-related lines
            if re.match(r'^(Software:|Social Media:|Industry Assets:|Assets:)', line, re.IGNORECASE):
                continue
            filtered_lines.append(line)
        
        # Process filtered lines
        for line in filtered_lines:
            # Skip section headers
            if any(k in line.lower().replace(' ', '') for k in section_header_keywords):
                continue
            # Skip contact info lines
            if any(p.search(line) for p in contact_patterns):
                continue
            # Check if this line starts a new experience entry
            if any(pattern.search(line) for pattern in self.job_title_patterns):
                # Save previous entry
                if current_entry:
                    experience_entries.append(current_entry)
                # Start new entry
                current_entry = Experience(
                    title=line,
                    company='',
                    start_date=None,
                    end_date=None,
                    description=[],
                    achievements=[]
                )
            elif current_entry:
                # Try to extract dates
                dates = self._extract_dates(line)
                if dates:
                    if not current_entry.start_date:
                        current_entry.start_date = dates[0]
                    if len(dates) > 1:
                        current_entry.end_date = dates[1]
                # Check for achievements
                elif line.startswith('•') or line.startswith('-'):
                    current_entry.achievements.append(line.lstrip('•- '))
                # Otherwise, add to description
                else:
                    if not current_entry.company:
                        current_entry.company = line
                    else:
                        current_entry.description.append(line)
        # Add the last entry
        if current_entry:
            experience_entries.append(current_entry)
        return experience_entries

    def _extract_dates(self, text: str) -> List[str]:
        """Extract dates from text."""
        dates = []
        for pattern in self.date_patterns:
            matches = pattern.finditer(text)
            for match in matches:
                month = match.group('month') if 'month' in match.groupdict() else None
                year = match.group('year')
                if month:
                    dates.append(f"{month} {year}")
                else:
                    dates.append(year)
        return dates

    def parse(self, file_path: str) -> ParsedResume:
        """Parse a resume file and extract structured information."""
        try:
            raw = self._extract_text(file_path) or ""
            self.raw_text = raw
            text = self._preprocess_text(raw)
            # Use new section splitter for skills only
            sections_new = self._extract_sections(text)
            # Use old section splitter for education
            sections_old = self._extract_sections_old(text)
            skills     = self._parse_skills(    sections_new.get('skills',    ''), raw)
            education  = self._parse_education( sections_old.get('education', '' ))
            # --- Experience extraction using a new regex approach ---
            exp_pattern = re.compile(
                r'(?is)^[ \t]*(?:employment[\s-]*history|experience)[ \t\-:]*\n+(.*?)(?=^[ \t]*(?:education|skills|languages|profile)\b|\Z)',
                re.MULTILINE
            )
            m = exp_pattern.search(text)
            exp_text = ""
            if m:
                exp_text = m.group(1).strip()
                # Post-process: remove lines before the first job title
                lines = exp_text.splitlines()
                start_idx = 0
                for i, line in enumerate(lines):
                    if any(p.search(line) for p in self.job_title_patterns):
                        start_idx = i
                        break
                exp_text = '\n'.join(lines[start_idx:]).strip()
            else:
                # Fallback: take everything before the first Education line
                lines = text.splitlines()
                edu_start = next(
                    (i for i, L in enumerate(lines)
                     if re.search(r'\b(University|Universit[àa]|Institute)\b', L, re.IGNORECASE)),
                    len(lines)
                )
                exp_text = "\n".join(lines[:edu_start]).strip()
            experience = self._parse_experience(exp_text)
            # After extracting skills, also look for 'Software:', 'Social Media:', or 'Industry Assets:' lines anywhere in the text
            extra_skill_lines = []
            for line in text.splitlines():
                m = re.match(r'^(Software:|Social Media:|Industry Assets:)(.*)', line.strip(), re.IGNORECASE)
                if m:
                    # Extract the part after the colon
                    skills_part = m.group(2).strip()
                    # Split by commas and strip
                    extra_skill_lines.extend([s.strip() for s in skills_part.split(',') if s.strip()])
            # Add these to the skills list, deduplicated
            skills = list(dict.fromkeys(skills + extra_skill_lines))
            return ParsedResume(
                raw_text   = raw,
                skills     = skills,
                education  = education,
                experience = experience
            )
        except Exception as e:
            logger.error(f"Error parsing resume {file_path}: {str(e)}")
            raise

    def _calculate_completeness(self, sections: Dict[str, str]) -> float:
        """
        Calculate the completeness score of the parsed resume.
        """
        total_sections = len(self.section_patterns)
        filled_sections = sum(1 for section, content in sections.items() if content)
        return filled_sections / total_sections

if __name__ == '__main__':
    import sys
    parser = ResumeParser()
    if len(sys.argv) < 2:
        print("Usage: python resume_parser.py path/to/resume.pdf|docx")
        sys.exit(1)
    path = sys.argv[1]
    result = parser.parse(path)
    print("\nSkills:")
    for skill in result.skills:
        print(f"- {skill}")
    print("\nEducation:")
    for edu in result.education:
        print(f"- {edu.degree} at {edu.institution}")
        if edu.start_date or edu.end_date:
            print(f"  {edu.start_date or ''} - {edu.end_date or 'Present'}")
        if edu.gpa:
            print(f"  GPA: {edu.gpa}")
    print("\nExperience:")
    for exp in result.experience:
        print(f"- {exp.title} at {exp.company}")
        if exp.start_date or exp.end_date:
            print(f"  {exp.start_date or ''} - {exp.end_date or 'Present'}")
        if exp.achievements:
            print("  Achievements:")
            for achievement in exp.achievements:
                print(f"  • {achievement}")
