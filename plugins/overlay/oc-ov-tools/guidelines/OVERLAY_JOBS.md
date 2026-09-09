# Overlay jobs

> LAYERS OVER: nothing — no core equivalent. Core SERVICE_GUIDELINES and CODE_QUALITY apply.
> CORE BASELINE: oc-be-tools 1.17.0

## Discovery is by type, not package

Core finds jobs as CDI/EJB beans extending `Job`. **Any package works** — vertical jobs commonly live
in `com.oc.<domain>`, while jobs that extend or sit alongside a core job use `org.meveo.admin.job`.
Do not move a job just to match a package convention.

## The Job / JobBean pair

```java
@Stateless
public class XxxJob extends Job {

    public static final String JOB_INSTANCE_XXX_JOB = "JobInstance_XxxJob";

    @Inject private XxxJobBean xxxJobBean;

    @Override
    @TransactionAttribute(TransactionAttributeType.NEVER)
    protected void execute(JobExecutionResultImpl result, JobInstance jobInstance) throws BusinessException {
        xxxJobBean.execute(result, jobInstance);
    }

    @Override
    public JobCategoryEnum getJobCategory() { return JobCategoryEnum.INVOICING; }

    @Override
    public Map<String, CustomFieldTemplate> getCustomFields() { /* … */ }
}
```

The `Job` class stays thin: category, custom-field templates, and delegation. All work goes in the
`XxxJobBean extends BaseJobBean`, annotated
`@Interceptors({ JobLoggingInterceptor.class, PerformanceInterceptor.class })` and
`@TransactionAttribute(NEVER)` so it manages its own transactions.

Unlike scripts, jobs **are** CDI beans — `@Inject` works normally here.

## Custom fields

Declare each in `getCustomFields()` with `setAppliesTo("JobInstance_<JobName>")` matching the
`JOB_INSTANCE_*` constant. Read them with:

```java
Long nbRuns = (Long) this.getParamOrCFValue(jobInstance, "nbRuns", -1L);
```

## Report results properly

Set `result.setNbItemsToProcess(...)`, then
`setNbItemsCorrectlyProcessed` / `setNbItemsProcessedWithError`, and call `registerSucces()`.
A job that catches everything and reports nothing looks green while doing nothing.

## A new job class is not a runnable job

Deploying the class only makes the **template** available. The job does not run until a `JobInstance`
exists. Those are created through the environment-setup Postman collections (the jobs/workflow
collection, or the MACO job create-or-update collection). **Say so in the hand-off** — this is the most
common "my job never ran" cause.
