# Workspace index

Every row below is generated from `registry/workspaces/*/project.json`. Edit the records,
then run `render`.

<!-- BEGIN GENERATED:workspace-index -->
| Workspace | Status | Summary | Depends on |
|---|---|---|---|
| Alpha | Active | A synthetic analytics workspace with two pipelines | none |
| Beta | Paused | A synthetic reporting workspace that consumes Alpha output | Alpha |
<!-- END GENERATED:workspace-index -->

## Reading this index

`Depends on` names the workspace whose records must be current before this one is worked.
