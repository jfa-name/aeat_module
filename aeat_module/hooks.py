app_name = "aeat_module"
app_title = "Aeat Module"
app_publisher = "soporte@jfa.name"
app_description = "Módulo para la AEAT"
app_email = "soporte@jfa.name"
app_license = "MIT"

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/aeat_module/css/aeat_module.css"
# app_include_js = "/assets/aeat_module/js/aeat_module.js"

# include js, css files in header of web template
# web_include_css = "/assets/aeat_module/css/aeat_module.css"
# web_include_js = "/assets/aeat_module/js/aeat_module.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "aeat_module/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# doctype_js = {"doctype" : "public/js/doctype.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "aeat_module.utils.jinja_methods",
# 	"filters": "aeat_module.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "aeat_module.install.before_install"
# after_install = "aeat_module.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "aeat_module.uninstall.before_uninstall"
# after_uninstall = "aeat_module.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "aeat_module.utils.before_app_install"
# after_app_install = "aeat_module.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "aeat_module.utils.before_app_uninstall"
# after_app_uninstall = "aeat_module.utils.after_app_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "aeat_module.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# DocType Class
# ---------------
# Override standard doctype classes

# override_doctype_class = {
# 	"ToDo": "custom_app.overrides.CustomToDo"
# }

# Document Events
# ---------------
# Hook on document methods and events

# doc_events = {
# 	"*": {
# 		"on_update": "method",
# 		"on_cancel": "method",
# 		"on_trash": "method"
# 	}
# }

# Scheduled Tasks
# ---------------

# scheduler_events = {
# 	"all": [
# 		"aeat_module.tasks.all"
# 	],
# 	"daily": [
# 		"aeat_module.tasks.daily"
# 	],
# 	"hourly": [
# 		"aeat_module.tasks.hourly"
# 	],
# 	"weekly": [
# 		"aeat_module.tasks.weekly"
# 	],
# 	"monthly": [
# 		"aeat_module.tasks.monthly"
# 	],
# }

# Testing
# -------

# before_tests = "aeat_module.install.before_tests"

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "aeat_module.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "aeat_module.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["aeat_module.utils.before_request"]
# after_request = ["aeat_module.utils.after_request"]

# Job Events
# ----------
# before_job = ["aeat_module.utils.before_job"]
# after_job = ["aeat_module.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"aeat_module.auth.validate"
# ]
