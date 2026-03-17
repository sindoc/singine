package singine.activity.photo;

import singine.activity.ActivityTemplate;
import singine.activity.Policy;
import singine.activity.Taxonomy;

import java.util.LinkedHashMap;
import java.util.Map;

/**
 * Activity taxonomy bindings for Singine photo review workflows.
 *
 * <p>The Python CLI surface under {@code singine photo} is the operational
 * entry point, while these JVM classes provide the canonical activity,
 * taxonomy, and policy shapes used by generated documentation and future JVM
 * orchestration paths.
 */
public final class PhotoReviewActivities {

    private PhotoReviewActivities() {
    }

    /** Shared taxonomy for photo review export activities. */
    public static final class PhotoReviewExportTaxonomy implements Taxonomy {
        /** Singleton taxonomy instance. */
        public static final PhotoReviewExportTaxonomy INSTANCE = new PhotoReviewExportTaxonomy();

        private PhotoReviewExportTaxonomy() {
        }

        @Override public String getId() { return "taxonomy-singine-photo-review-export"; }
        @Override public String getName() { return "Photo Review Export"; }
        @Override public String getDomain() { return "media-review"; }
        @Override public String getCategory() { return "photo-review"; }
        @Override public String getSubcategory() { return "review-export"; }

        @Override
        public Map<String, String> getLabels() {
            Map<String, String> labels = new LinkedHashMap<>();
            labels.put("en", "Photo Review Export");
            labels.put("fr", "Export de revue photo");
            labels.put("nl", "Foto review-export");
            return labels;
        }

        @Override
        public String toXml() {
            return "<taxonomy id=\"" + getId() + "\" domain=\"" + getDomain()
                + "\" category=\"" + getCategory() + "\" subcategory=\"" + getSubcategory()
                + "\"><label lang=\"en\">" + getName() + "</label></taxonomy>";
        }

        @Override
        public String toEdn() {
            return "{:taxonomy/id \"" + getId()
                + "\" :taxonomy/domain \"" + getDomain()
                + "\" :taxonomy/category \"" + getCategory()
                + "\" :taxonomy/subcategory \"" + getSubcategory()
                + "\" :taxonomy/labels {:en \"" + getName() + "\"}}";
        }
    }

    /** Shared policy for local photo review generation. */
    public static final class LocalPhotoReviewPolicy implements Policy {
        /** Singleton policy instance. */
        public static final LocalPhotoReviewPolicy INSTANCE = new LocalPhotoReviewPolicy();

        private LocalPhotoReviewPolicy() {
        }

        @Override public String getId() { return "policy-singine-photo-local-review-01"; }
        @Override public String getName() { return "Local Photo Review Export Policy"; }
        @Override public String getDecision() { return "approved"; }

        @Override
        public String getRationale() {
            return "Approved for local Apple Photos review exports and deterministic fixture generation.";
        }

        @Override
        public Map<String, Object> apply(Map<String, Object> context) {
            Map<String, Object> out = new LinkedHashMap<>(context);
            out.put(":policy/id", getId());
            out.put(":policy/decision", getDecision());
            out.put(":policy/runtime", "local-photo-review");
            return out;
        }

        @Override
        public String toXml() {
            return "<policy id=\"" + getId() + "\" decision=\"" + getDecision()
                + "\"><name>" + getName() + "</name><rationale>" + getRationale()
                + "</rationale></policy>";
        }

        @Override
        public String toEdn() {
            return "{:policy/id \"" + getId()
                + "\" :policy/decision \"" + getDecision()
                + "\" :policy/rationale \"" + getRationale().replace("\"", "\\\"") + "\"}";
        }
    }

    /** JVM metadata template for the export-review CLI activity. */
    public static final class ExportReviewActivity extends ActivityTemplate {
        /** Singleton activity template instance. */
        public static final ExportReviewActivity INSTANCE = new ExportReviewActivity();

        private ExportReviewActivity() {
        }

        @Override public String getId() { return "activity-photo-export-review-01"; }
        @Override public String getName() { return "Export City Review JPEGs from Apple Photos"; }

        @Override
        public String getDescription() {
            return "Query Apple Photos by city-labelled moments and emit lightweight review JPEGs with manifest and path lists.";
        }

        @Override public Taxonomy getTaxonomy() { return PhotoReviewExportTaxonomy.INSTANCE; }
        @Override public Policy getPolicy() { return LocalPhotoReviewPolicy.INSTANCE; }
    }

    /** JVM metadata template for the deterministic photo test case generator. */
    public static final class GenerateTestCaseActivity extends ActivityTemplate {
        /** Singleton activity template instance. */
        public static final GenerateTestCaseActivity INSTANCE = new GenerateTestCaseActivity();

        private GenerateTestCaseActivity() {
        }

        @Override public String getId() { return "activity-photo-test-case-01"; }
        @Override public String getName() { return "Generate Photo Review Export Test Case"; }

        @Override
        public String getDescription() {
            return "Create a deterministic Apple Photos fixture and linked activity metadata for singine photo demos and tests.";
        }

        @Override public Taxonomy getTaxonomy() { return PhotoReviewExportTaxonomy.INSTANCE; }
        @Override public Policy getPolicy() { return LocalPhotoReviewPolicy.INSTANCE; }
    }
}
