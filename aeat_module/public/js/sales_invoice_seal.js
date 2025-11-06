frappe.ui.form.on('Sales Invoice', {
    refresh: function(frm) {
        // show seal status
        if (frm.doc.seal_status) {
            frm.set_intro(`<strong>Seal:</strong> ${frm.doc.seal_status}`);
        }
        // add button to verify or export
        if (frm.doc.docstatus===1) {
            frm.add_custom_button(__('Ver evidencia/validar sello'), function() {
                frappe.call({
                    method: 'aeat_module.api.export_aeat_package',
                    args: { invoice_names: frm.doc.name },
                    callback: function(r) {
                        // download handled by server response
                    }
                });
            }, __('AEAT'));
        }
    }
});
